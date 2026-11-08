"""Reuse the checked opening assembly pipeline with the new visual edition."""
from pathlib import Path
import importlib.util

path = Path(__file__).with_name('assemble-opening.py')
spec = importlib.util.spec_from_file_location('relay_opening_assembly', path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.OUT = path.parents[1] / 'demo/opening-v4'
module.main()
