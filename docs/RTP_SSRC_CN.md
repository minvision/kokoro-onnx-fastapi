# RTP 语音传输中的 SSRC 说明

## 什么是 SSRC？

**SSRC (Synchronization Source)** 即同步源标识符，是 RTP (Real-time Transport Protocol，实时传输协议) 协议头中的一个 32 位字段。

## SSRC 的含义和作用

SSRC 用于**唯一标识 RTP 会话中的一个音频/视频流源**。其主要作用包括：

1. **流标识**：在同一个 RTP 会话中区分不同的媒体源（例如多个参与者的音频流）
2. **同步参考**：接收端使用 SSRC 来识别属于同一个源的所有数据包
3. **冲突检测**：当检测到 SSRC 冲突时，发送端需要更换 SSRC 值
4. **流绑定**：将 RTP 数据流与 RTCP 报告关联起来

## SSRC 值是否递增？

**否，SSRC 值在整个流传输过程中保持不变，不会递增。**

### RTP 数据包中递增的字段

虽然 SSRC 不递增，但 RTP 协议中有其他字段会递增：

| 字段 | 是否递增 | 递增规则 | 用途 |
|------|----------|----------|------|
| **SSRC** | ❌ 否 | 流开始时随机生成，之后保持不变 | 标识流源 |
| **序列号 (Sequence Number)** | ✅ 是 | 每个数据包递增 1 | 检测丢包和重排序 |
| **时间戳 (Timestamp)** | ✅ 是 | 按采样数递增 | 同步播放和计算抖动 |

### 代码示例

以下是本项目中 RTP 流实现的关键代码片段（来自 `.github/workflows/create_rtp_pr.yml`）：

```python
# SSRC 在流开始时随机生成一次
ssrc = random.getrandbits(32)

# 序列号和时间戳初始化
seq = random.randint(0, 0xFFFF)
timestamp = random.randint(0, 0x7FFFFFFF)

# 发送每个数据包时
while True:  # 简化示意
    # 构建 RTP 头部，使用相同的 ssrc
    header = _build_rtp_header(
        seq & 0xFFFF,           # 序列号（会递增）
        timestamp & 0xFFFFFFFF, # 时间戳（会递增）
        ssrc,                    # SSRC（不变）
        payload_type,
        marker
    )
    
    # 发送数据包
    transport.sendto(header + payload)
    
    # 序列号递增 1
    seq = (seq + 1) & 0xFFFF
    
    # 时间戳按音频采样数递增
    timestamp = (timestamp + samples_per_packet) & 0xFFFFFFFF
```

## RTP 头部结构

```
 0                   1                   2                   3
 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|V=2|P|X|  CC   |M|     PT      |       序列号 (Sequence)        |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                        时间戳 (Timestamp)                      |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                     SSRC (Synchronization Source)             |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
```

## 实际应用示例

### 场景：音频流传输

假设发送一个 8kHz 采样率的音频流，每个数据包包含 160 个采样点（20ms）：

| 数据包 # | 序列号 (Seq) | 时间戳 (Timestamp) | SSRC | 说明 |
|---------|-------------|-------------------|------|------|
| 1 | 12345 | 1000000 | **0x9A3B5C7D** | 初始值 |
| 2 | 12346 (+1) | 1000160 (+160) | **0x9A3B5C7D** | SSRC 不变 |
| 3 | 12347 (+1) | 1000320 (+160) | **0x9A3B5C7D** | SSRC 不变 |
| 4 | 12348 (+1) | 1000480 (+160) | **0x9A3B5C7D** | SSRC 不变 |
| ... | ... | ... | **0x9A3B5C7D** | SSRC 始终不变 |

## 常见误解

### ❌ 错误理解
- SSRC 每个数据包递增
- SSRC 用于排序数据包
- SSRC 随时间变化

### ✅ 正确理解
- SSRC 在流的生命周期内保持不变
- 序列号用于排序和检测丢包
- 时间戳用于同步和播放
- SSRC 仅在流重启或发生冲突时才会改变

## 参考资料

- [RFC 3550 - RTP: A Transport Protocol for Real-Time Applications](https://tools.ietf.org/html/rfc3550)
- [RFC 3551 - RTP Profile for Audio and Video Conferences](https://tools.ietf.org/html/rfc3551)

## 本项目中的实现

本项目的 RTP 流实现位于计划添加的 `src/utils/stream_rtp_streaming.py` 文件中。该实现：

- 使用 32 位随机数生成 SSRC
- 在整个流传输过程中保持 SSRC 不变
- 正确递增序列号和时间戳
- 支持 L16 音频格式的 RTP 封装

## 总结

**SSRC（同步源标识符）是 RTP 协议中用于标识流源的唯一标识符，在整个流传输过程中保持不变，不会递增。真正递增的是序列号（每个包 +1）和时间戳（按采样数递增）。**
