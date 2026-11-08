"""Operator-only local demo enrollment for Switch Console's native runtime.

The privileged native environment is read only during setup. Runtime config
contains scoped agent keys and fictional demo users, never Core/DB admin keys.
This creates private rooms in the existing local tenant, not a separate tenant.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import secrets
import shlex
import subprocess
import tempfile
import time
from typing import Any
import uuid

import httpx


class BootstrapError(RuntimeError):
    """Safe setup failure without credentials or arbitrary remote response text."""


_NATIVE = Path(os.environ.get("RELAY_SWITCH_RUNTIME", str(Path.home() / "Library/Application Support/switchdash/local-switch-server"))).expanduser()
_BUNDLE = Path(os.environ.get("RELAY_SWITCH_BUNDLE", "/Applications/Switch Console.app/Contents/Resources/local-server")).expanduser()


def _save(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    fd, temporary = tempfile.mkstemp(prefix=".support-lab-switch-setup-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(data, stream, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _env(path: Path) -> dict[str, str]:
    values = {}
    for line in path.read_text().splitlines():
        if not line.strip() or line.lstrip().startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if value.startswith(("'", '"')):
            parts = shlex.split(value)
            value = parts[0] if parts else ""
        values[key.strip()] = value
    return values


# Runs only as an operator setup subprocess with bundled asyncpg/cryptography.
# Stdout is captured in memory, never printed or added wholesale to config.
_METADATA = r'''
import asyncio,json,os,shlex,sys
from pathlib import Path
import asyncpg
from switch_core.keys import Keyring
async def main():
 req=json.load(sys.stdin); env={}
 for line in Path(req['env_path']).read_text().splitlines():
  if line.strip() and not line.lstrip().startswith('#') and '=' in line:
   key,value=line.split('=',1)
   if value.startswith(('"',"'")):
    parts=shlex.split(value);value=parts[0] if parts else ''
   env[key.strip()]=value
 con=await asyncpg.connect(host=env['DB_HOST'],port=int(env['DB_PORT']),
  user=env.get('DB_OWNER_USER') or env['DB_USER'],
  password=env.get('DB_OWNER_PASSWORD') or env['DB_PASSWORD'],database=env['DB_NAME'])
 try:
  async with con.transaction(readonly=True):
   if req['mode']=='bridge':
    if req.get('bridge_id'):
     row=await con.fetchrow('SELECT id,tenant_id,connection_config FROM collaboration_bridges WHERE id=$1 AND type=$2',req['bridge_id'],'mattermost')
    else:
     row=await con.fetchrow('SELECT id,tenant_id,connection_config FROM collaboration_bridges WHERE type=$1 ORDER BY is_default DESC LIMIT 1','mattermost')
    if not row: raise ValueError('missing local Mattermost bridge')
    config=row['connection_config'];config=json.loads(config) if isinstance(config,str) else config
    if isinstance(config,dict) and set(config)=={'_enc'}:
     ring=Keyring.parse(env['SECRET_KEYS'],legacy_secret=env.get('JWT_SECRET_KEY'))
     config=json.loads(ring.decrypt(config['_enc']))
    result={'bridge_id':row['id'],'tenant_id':row['tenant_id'],'connection_config':config}
   else:
    humans=await con.fetch('SELECT c.id AS client_id,c.matrix_user_id AS actor_id,e.id AS external_identity_id,e.external_user_id FROM external_users e JOIN clients c ON c.id=e.client_id AND c.tenant_id=e.tenant_id WHERE e.bridge_id=$1 AND e.external_user_id=ANY($2::text[])',req['bridge_id'],req['human_ids'])
    agents=await con.fetch('SELECT a.id,c.id AS client_id,c.matrix_user_id AS actor_id,a.owner_id FROM agents a JOIN clients c ON c.id=a.client_id AND c.tenant_id=a.tenant_id WHERE a.id=ANY($1::text[])',req['agent_ids'])
    result={'humans':[dict(r) for r in humans],'agents':[dict(r) for r in agents]}
   print(json.dumps(result))
 finally: await con.close()
try: asyncio.run(main())
except Exception:
 print('Native setup metadata lookup failed.',file=sys.stderr);sys.exit(1)
'''


def _metadata(mode: str, **kwargs: Any) -> dict:
    environment = dict(os.environ)
    environment["PYTHONPATH"] = os.pathsep.join([
        str(_BUNDLE / "switch/site-packages"), str(_BUNDLE / "switch/src/core")])
    request = {"mode": mode, "env_path": str(_NATIVE / "native/run/switch-core.env"), **kwargs}
    try:
        result = subprocess.run([str(_BUNDLE / "python/bin/python3"), "-c", _METADATA],
                                input=json.dumps(request), capture_output=True, text=True,
                                timeout=20, env=environment)
        if result.returncode:
            raise BootstrapError("Native setup metadata lookup failed; check the local Switch runtime.")
        return json.loads(result.stdout)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        raise BootstrapError("Could not inspect the installed native Switch runtime.") from None


class _API:
    def __init__(self, base: str):
        self.client = httpx.Client(base_url=base.rstrip("/"), timeout=40, follow_redirects=False)

    def call(self, method: str, path: str, data: dict | None = None, *, allow: tuple[int, ...] = ()):
        try:
            response = self.client.request(method, path, json=data)
        except httpx.HTTPError:
            raise BootstrapError("A local setup request failed; rerun setup to reconcile saved resources.") from None
        if response.status_code in allow:
            return response
        if response.status_code >= 300:
            raise BootstrapError(f"Local setup API refused {method} {path.split('?')[0]} (status {response.status_code}).")
        return response

    def json(self, method: str, path: str, data: dict | None = None):
        response = self.call(method, path, data)
        try:
            return response.json()
        except ValueError:
            raise BootstrapError("Local setup API returned an invalid result.") from None

    def gateway_login(self, email: str, password: str) -> dict:
        return self.json("POST", "/gateway/auth/login", {"email": email, "password": password})

    def mm_login(self, login_id: str, password: str) -> tuple[dict, str]:
        response = self.call("POST", "/api/v4/users/login", {"login_id": login_id, "password": password})
        token = response.headers.get("Token")
        if not token:
            raise BootstrapError("Mattermost did not return an authentication token.")
        self.client.headers["Authorization"] = "Bearer " + token
        return response.json(), token

    def close(self):
        self.client.close()


