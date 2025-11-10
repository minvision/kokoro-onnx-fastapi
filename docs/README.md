# Documentation Index / 文档索引

This directory contains technical documentation for the kokoro-onnx-fastapi project.

本目录包含 kokoro-onnx-fastapi 项目的技术文档。

## Available Documents / 可用文档

### RTP Protocol / RTP 协议

- **[RTP_SSRC_CN.md](RTP_SSRC_CN.md)** - RTP 语音传输中的 SSRC 说明（中文）
  - Explains what SSRC (Synchronization Source) represents in RTP voice packet transmission
  - Clarifies that SSRC does NOT increment per packet
  - Includes code examples, RTP header structure, and practical scenarios
  - 解释 RTP 协议中 SSRC（同步源标识符）的含义
  - 说明 SSRC 在传输过程中不会递增
  - 包含代码示例、RTP 头部结构和实际应用场景

- **[RTP_SSRC_EN.md](RTP_SSRC_EN.md)** - RTP SSRC Explanation for Voice Transmission (English)
  - English version of the SSRC documentation
  - Comprehensive explanation with examples and diagrams
  - References to RFC 3550 and RFC 3551
  - SSRC 文档的英文版本
  - 包含示例和图表的全面说明
  - 引用 RFC 3550 和 RFC 3551 标准

## Quick Reference / 快速参考

### Common Question: Does SSRC increment per packet?

**Answer:** ❌ **NO**

- **SSRC**: Constant throughout the stream (32-bit random identifier)
- **Sequence Number**: ✅ Increments by 1 per packet
- **Timestamp**: ✅ Increments by sample count per packet

### 常见问题：SSRC 每个包递增吗？

**答案：** ❌ **不会递增**

- **SSRC（同步源）**: 在整个流中保持不变（32位随机标识符）
- **序列号**: ✅ 每个包递增 1
- **时间戳**: ✅ 按采样数递增

## Contributing / 贡献

If you find any issues or have suggestions for improving the documentation, please open an issue or submit a pull request.

如果您发现任何问题或对改进文档有建议，请提交 issue 或 pull request。
