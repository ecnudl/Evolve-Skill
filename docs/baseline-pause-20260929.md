# 2026-09-29 暂停请求与恢复交接

记录时间：2026-09-29 11:01（Asia/Shanghai）。用户要求暂停实验，准备盒盖休眠。

**状态：已停止本次新增实验操作，但未能向 Linux 下发暂停，不能声称远端已暂停。**

## 本次实际检查

- 原样 `ssh PJ-CL4MIND-DULIN` 返回认证前连接重置；交互终端重试和单次限时重试同样失败。
- `ssh -O check PJ-CL4MIND-DULIN` 确认当前 ControlMaster socket 不存在。上午成功复用连接的历史事实保持不变，不能用它推断此刻可连接。
- 没有读取到当前远端进程、容器或结果；没有成功发送停止信号。
- 本机检查未发现本轮本地 Python 实验调度进程。未改变 Clash、VPN、路由、SSH 配置或实验协议；未启动新模型调用，未删除、覆盖结果。

Linux 的 tmux 后台任务不会因本机盒盖自动暂停。上午已启动的有限接续队列可能继续工作或已经进入下一项；当前状态未知。

## 已有可靠快照，不是本次实时进度

本地保留的远端汇总采样时间为 2026-09-29 10:14:38（Asia/Shanghai），路径为 `outputs/continual_eval/resume_20260929/latest-results.md`。

| 运行 | 该快照的计数 |
| --- | --- |
| SearchQA | 800 位置完成：552 pass、242 fail、6 unknown |
| KOR-Bench | 1000 位置完成：639 pass、201 fail、160 unknown |
| ALFWorld B | 78 位置中 63 available、12 unknown、3 尚无终态；尚未评分 |
| BigCodeBench A | 800 预测完成；656 位置已评分：335 pass、319 fail、2 unknown，144 待评分 |
| Spreadsheet B | 160 位置，快照时尚未启动 |

available 不代表正确。上述旧计数不能作为 11:01 的完成数量或暂停断点；恢复时以远端实际回执为准。

## 恢复时优先核查

1. 用户再次明确 resume 后，先用原样 SSH 别名检查连接。不要自动重新创建旧运行、重抽样或删除开放意图。
2. 核查 `continual-followup-20260929`、`continual-results-20260929`、`continual-bcb-score-resume-20260929`、`continual-alf-resume-20260929` 等准确 tmux 会话和实际进程树；名称只是既有启动记录，不是此刻仍存在的证明。
3. 读取 `/root/continual-resume-20260929/results/latest.md`、正式报告及回执，确认 BCB/ALF 是否已经完成、Sheet 是否已经启动或完成。
4. 若届时仍需暂停，应先控制接续调度，再停止实验：`after_resume_20260929.sh` 没有暂停标志检查，单独停止前序任务可能触发 Sheet 启动。不要使用匹配所有 Python/tmux/Docker 的宽泛终止命令。
5. 完整终态保留并回放；只有开放意图的任务须先核查实际进程及执行清理。丢失环境的中断记录不能直接重采样，按对应恢复协议保留基础设施 unknown。

远端运行根目录：

- `/root/continual-noskill-bcb-20260928-a/run`
- `/root/continual-noskill-alf-20260928-b/run`
- `/root/continual-noskill-sheet-20260928-b/run`
- `/root/continual-learning-qualification-20260929-a`（零模型环境资格检查，不等于学习实验）

本次没有新的实验效果结论，也没有 Git 提交或推送。[上午恢复记录](baseline-resume-20260929.md)和[结果摘要](noskill-baseline-summary-20260928.md)保留历史来源。
