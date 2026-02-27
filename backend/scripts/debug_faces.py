"""Quick diagnostic: inspect face types in the motorholder IGES file."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pathlib import Path

FILE = Path(__file__).parent.parent / "local_uploads" / "uploads" / \
    "1dc0de18-cf57-4d8d-8976-a53ed6ddf6ce" / \
    "0af7d876-d89b-4d0f-9d66-38b11c8626db" / "motorholder.IGS"

from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_FACE
from OCP.TopoDS import TopoDS
from OCP.BRep import BRep_Tool
from OCP.GeomAdaptor import GeomAdaptor_Surface
from OCP.IGESControl import IGESControl_Reader
from OCP.IFSelect import IFSelect_RetDone

# Load
reader = IGESControl_Reader()
status = reader.ReadFile(str(FILE))
assert status == IFSelect_RetDone, f"Failed with status {status}"
reader.TransferRoots()
shape = reader.OneShape()
print(f"Shape loaded: {shape}")

# Count faces
explorer = TopExp_Explorer(shape, TopAbs_FACE)
total = 0
type_counts = {}
while explorer.More():
    face = TopoDS.Face_s(explorer.Current())
    surface = BRep_Tool.Surface_s(face)
    if surface is not None:
        adaptor = GeomAdaptor_Surface(surface)
        stype = adaptor.GetType()
        sname = str(stype)
        type_counts[sname] = type_counts.get(sname, 0) + 1
    else:
        type_counts["NULL_SURFACE"] = type_counts.get("NULL_SURFACE", 0) + 1
    total += 1
    explorer.Next()

print(f"\nTotal faces: {total}")
print("Face types:")
for name, count in sorted(type_counts.items(), key=lambda x: -x[1]):
    print(f"  {name}: {count}")
