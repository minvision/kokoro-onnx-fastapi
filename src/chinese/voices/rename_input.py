# rename_input.py
import onnx_graphsurgeon as gs
import onnx

model_path = "model.onnx"
out_path   = "model-renamed.onnx"

graph = gs.import_onnx(onnx.load(model_path))

# 找到旧输入节点
old_inp = None
for inp in graph.inputs:
    if inp.name == "input_ids":
        old_inp = inp
        break
if old_inp is None:
    raise RuntimeError("找不到名为 input_ids 的输入")

# 1. 新建同形状、同类型的输入，名字换成 tokens
new_inp = gs.Variable(
    name="tokens",
    dtype=old_inp.dtype,
    shape=old_inp.shape
)

# 2. 把所有用到 old_inp 的节点输入替换成 new_inp
for node in graph.nodes:
    node.inputs = [new_inp if i == old_inp else i for i in node.inputs]

# 3. 把 graph.inputs 里的 old_inp 换成 new_inp
graph.inputs = [new_inp if i == old_inp else i for i in graph.inputs]

# 4. 清理并导出
graph.cleanup()
onnx.save(gs.export_onnx(graph), out_path)
print(f"已保存为 {out_path}，输入名已改为 tokens")