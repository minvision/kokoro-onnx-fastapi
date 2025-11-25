# check_ir.py
import onnx, sys
m = onnx.load(sys.argv[1])
print("IR version :", m.ir_version)
print("Opset      :", [imp.version for imp in m.opset_import])