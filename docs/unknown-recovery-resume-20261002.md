# 10/2 unknown 修复续跑

## 午后本轮已完成：不需重复启动B或C

C完整160为79/55/26，较v8b恢复16未知（9 pass＋7 fail），118旧已知全保持；150闭合回执/142容器699.829924秒，0API/开放/清理未确认。独立调用冻结源report再核验，终态`b9b7709365171e8e1cd85086263c5271db048e9bd7fc5b73bf67374dc32fe1fa`；全部产物仍是原模型输出，没有新增学习反馈授权。

C交付侧车目录`/root/continual-unknown-frozen-gold-c-20261002-delivery`，已完成79/61/20的独立回顾性端到端统计；内容分未改。终态`165ebdd7c6d83fb65ff21d77aa5d0bd412770ee6ed8fa3e6e8889e45c8c9ba93`；1145份读取证据、源码及160行重新核验不变。B负对照与两轮原始结果、源码均保留，C与侧车完整目录已下载本地私有outputs，公开的只为受控汇总。

远端两个实验tmux已自然退出，Docker无残留实验容器；只读observer仍在，不提交实验。没有停止用户SSH master或改Clash。4093项完整离线回归通过、9项可选GEPA跳过；91项H窄修和88项交付测试另列。下一步如需替代引擎，应另行冻结协议，不再resume已完整结束的目录。[最终报告](unknown-recovery-results-20261002.md#午后恢复冻结h参考标签与交付分轴)

## 午后窄元数据资格通过、C完整重评已启动

B完整160终态51/41/68，协议`6b75a68…`、报告`828f69525b7183555fcce58314aa79d547766bc8a5681452187a05712114aa83`；已独立调用冻结report核对同hash。B不是覆盖改善，主要是23参考元数据被全局拒绝。交付侧车已实际完成，原内容不变，回顾性端到端51/47/62；旧v8b仍70/48/42。

新H v3仅认可严格包关系/单记录XLDAPR、cm1单格array与完整保存目标缓存，不动候选执行器或比较容差。91项本地相关测试通过，独审修复3个包声明链检查缺口。C新路径引擎34/34、评分18/18通过，79/80参考可用、1已知争议继续未知。

- 源码`/root/continual-unknown-frozen-gold-c-20261002-source`；H模块SHA`911d19a9857331eea86714bbaf063a95190d3e8b89170092b5d659aa9d79cd1f`。
- 资格`/root/continual-unknown-frozen-gold-c-20261002-q34/qualification.json`、`/root/continual-unknown-frozen-gold-c-20261002-scoreq/qualification.json`。
- 全160重评`/root/continual-unknown-frozen-gold-c-20261002-replay`，协议`8a5ed661af1e188d41d77019eb3e7dbef946cfa61149e6400df3c658002b612d`；tmux `frozen-gold-c-replay-20261002`，日志同输出根加`.log`。只操作这一新运行，不覆盖已闭合B。
- 同共享native锁；恢复前检查tmux、positions、intents、recalculations与reports，开放执行不重复提交。全部零API；无模型/Skill变化。

## 14:05 aTrust 恢复后的续跑

原 `ssh PJ-CL4MIND-DULIN` 与既有 master 可用。只读核验私有SSH目标走aTrust的`utun7`、既有VPN公网入口单地址路由走Wi-Fi `en0`；两个普通公网抽查目标仍走Clash。未修改路由、停止Clash或退出用户master。确认13:00启动失败未创建评分目录且无对应进程后，才补启动新评分。

- v2评分资格 **14/14通过**：10闭合回执、9容器/23.216166秒、0API/开放/清理未确认；此前34/34引擎资格复用，不重跑。
- 随后冻结并启动同80题×2完整160位置的零API重评；新目录`/root/continual-unknown-frozen-gold-b-20261002-replay`，协议`6b75a68db64fe646ad1b033e49eed36714f0301252fa5cc946e8cced7dfd750b`。不覆盖v8b或原分数。
- 新H清单80份中56可用、23因全局动态数组元数据限制未知、1已知参考争议。这个限制可能过拒已保存的显式单格缓存，正在单独审查；当前运行的源码与结果保持冻结，不为提高覆盖而临时改评分规则。
- 新交付分轴侧车通过78项自测及10项独立review，修正截断归因和实际生成代码堆栈行绑定；等待完整重评后另行生成回顾性端到端统计。
- 本地完整研究离线回归 **4044 passed / 9 skipped**，299.38秒；9跳过仍为未安装可选GEPA，不是通过。侧车独审10项另列。

[v1拒绝资格](results/unknown-sheet-frozen-gold-a-score-qualification-20261002.json) · [v2引擎资格](results/unknown-sheet-frozen-gold-b-engine-qualification-20261002.json) · [v2评分资格](results/unknown-sheet-frozen-gold-b-score-qualification-20261002.json)

## 13:00 用户关闭aTrust后的暂停断点

用户要求暂停，停止新开发、模型调用、远端启动与网络重试；没有修改Clash或终止用户SSH master。SSH最后两次均认证前关闭，故不冒称向Linux成功下发暂停命令。

- 新增`sheet_frozen_gold.py`、`replay_sheet_frozen_gold.py`及测试，原答案和v8b全160结果仍为70/48/42，没有新的全160成绩。
- 首套新路径引擎34/34通过（28容器63.565984秒）；评分v1为12/13通过、rejected（7容器16.378286秒）。候选False被Calc导出为公式，原保护正确拒绝；保留首次源码/回执，不放宽引擎。
- v2将H中0/False可读性与候选布尔字面量限制分开，共14控制，后者明确unknown。新路径引擎再次34/34通过（28容器82.266071秒）。v2评分tmux启动SSH返回255，**远端是否执行尚未确认**，不能重复启动。
- 本地相关521项完整通过；v2模块/CLI/独审56项通过。后启动的大套回归因用户暂停SIGINT，1727项已通过、exit2，**不是全套通过**。
- 交付分轴模块64项测试通过；新侧车脚本10项工程测试通过，六例本地核对5程序缺陷＋1契约歧义，0API/容器。侧车独审和全160远端运行尚未完成。
- 本机Excel16.113.3及字典禁宏/不更新链接选项存在；未启动Excel或打开工作簿，尚无已核实Windows Excel或隔离Mac评分环境。

### 恢复顺序与路径

先按AGENTS使用原SSH alias核验连接、tmux、进程、开放意图与清理，不重跑已闭合实验。

1. 原拒绝输出`/root/continual-unknown-frozen-gold-20261002-scoreq`及原源码`/root/continual-unknown-frozen-gold-20261002-source`保持不变。
2. 当前源码`/root/continual-unknown-frozen-gold-b-20261002-source`；引擎资格`/root/continual-unknown-frozen-gold-b-20261002-q34/qualification.json`。
3. 待核实评分输出`/root/continual-unknown-frozen-gold-b-20261002-scoreq`，日志同名`.log`，tmux名`frozen-gold-b-score-q-20261002`。先查protocol/qualification/intents；如未创建才用`python -m scripts.replay_sheet_frozen_gold qualify-score`启动。
4. 新评分14项全通过后，才`prepare`全160新目录；父`/root/continual-unknown-sheet-v8b-20261002-replay`，共享锁`/root/continual-baselines-long-20261001-study/native.lock`。本轮尚未发出prepare/run。
5. 远端Python`/root/miniconda3/envs/skill_validation/bin/python`，PYTHONPATH指当前新源码。旧34控制入口未改。
6. 模块v2 SHA`e0cbff8c05165433e9653863b3f70b7d81fccd3a6ab68bee28fad7c1254994a3`；新CLI SHA`243f81c818ed0f02b1864cf79685ed7691c34f867fb66d9cb398fd8299944465`。恢复时确认字节一致。
7. 待同步侧车`scripts/report_sheet_delivery_outcomes.py`及`delivery_outcomes.py`，先独审。资格JSON的两次SCP归档均失败，不能引用未下载的公开JSON。

以下为更早的续跑记录，保留当时状态。

**后续终态已核验**：10/2 10:32恢复连接后，KOR为7 pass/2 fail/1 unknown（10/10闭合），Sheet v7为63/46/51（160/160闭合）；均无开放回执或清理未确认。[完整结果与剩余修复](unknown-recovery-results-20261002.md)。以下保留续跑及中途断网时的实际快照。

## 断点核验

原 `ssh PJ-CL4MIND-DULIN` 可用；没有改动或重启 Clash。Linux 无残留实验进程或容器。10/1 暂停时的在途请求已正常结束，因此 KOR 截断恢复子集在续跑前为 **2/10 完成：1 pass、1 fail、0开放调用**，共2调用/2HTTP/61,376 tokens，2容器/3.548693秒，清理均确认。

原暂停标志移到 `PAUSE.saved-20261002` 保留，原协议和目录不变；在同一 Linux shell 执行 `proxy_on` 后已后台继续余下8个未提交位置。续跑仍为单并发，131072 token上限、read300/wall3600；不重复已完成位置，也不补抽完整fail。此处是选定失败位置的诊断，不能合并成统一预算基线。

## 代码及待验收边界

- 上次广泛回归的6个失败都发生于冻结资格的源码身份检查。静止源码下重跑 `test_continual_eval_frozen_rescore.py` 与参考资格测试，**36 passed**；与并发修改源码触发保护相符。并不意味着上次整个3750/6/9运行可以重标成全通过。
- 新代码提取器及其回放入口已独立review，相关两组测试共144 passed；补上取得共享锁后再次校验资产、绑定实际送入容器的字节后，76项相关测试通过。回放仅使用原始closed回复中的字面Python片段，原Prompt、代码内容和评分标准不改。完整160位置审计确认只有1个原unknown有实质提取变化（另158个只有边界空白字节差异，不重执行）；该题零API执行成功生成工作簿，但原v5评分仍因 `reference:unsupported_active_or_external_workbook` 返回unknown。1个容器、1.858031秒、清理确认。原160位置成绩不变，不把交付修复当成新增正确答案。[完整回执](results/unknown-sheet-fenced-replay-20261002.json)
- v6a工作簿资格18/20被拒绝，失败记录保留。v6b支持真实导出的自定义General样式，但仍不足：公式单元格也被Calc自动改成日期读取类型。新的v7比较视图只调整符合条件的样式，不改原公式、数值缓存或控制expected，保留真正日期和格式观察保护。旧20项输入字节/预期逐项核验复用，另加3个日期/错误数值控制，真实Linux **23/23资格通过**；21容器/45.106300秒、0API/0开放/0清理未确认。[独立资格](results/unknown-sheet-v7-qualification-20261002.json)。随后已在Linux后台启动原80题×2全部160位置的零API重评，不仅重评unknown；最近已读取14/160，终态未核验，旧分数不回写。
- Sheet完整面板中唯一closed length已完成一次独立恢复：原提示词、提取和v5评分不变，131072上限下生成完整工作簿，最终 **1 fail、0 unknown**。1调用/1HTTP/3,238 tokens；3容器/4.475606秒，清理全部确认。原调用报告65,919 tokens；没有同预算重采样对照，不能把此次完整交付归因于增加上限，更不能把消除unknown写成提分。[独立回执](results/unknown-sheet-length-recovery-20261002.json)

运维方面已启用只读 `experiment-observer-v4`，支持新恢复器各自的intent/call/result布局；每60秒记录累计值，不重复统计API缓存，也不提交、恢复或修复任务。观测是运维状态，不代替带哈希的正式回执。

## 回归测试与最新限制

完整research-offline CI命令加v7测试：**3843 passed / 9 skipped / 0 failed**，298.74秒。运行期间外围脚本与v7测试曾补来源绑定，完成后又在最终冻结脚本下重跑相关两文件：**32 passed**。9个skip均因本地未安装可选pinned GEPA，不写成通过。静态Ruff及diff check通过；本地缺少MkDocs，文档发布边界测试另为1 skip，未宣称严格站点构建通过。

独立review发现并已修复：旧q20其余17个控制不能仅核对名字，还必须与传入q17逐项核对实际字节及expected，防止混用两套各自合法的控制集。最终脚本SHA为 `d2ddc0b0051d5ba51080696501f4e818c76ca8ee4cc31369addfeb8466e27bcd`，v7模块SHA为 `717bfb2e3363cf79ee803bff93746c47b262f2d6831839afd56d2f5558ae523d`；修复后独审无阻塞。

KOR最近已核验快照为4/10闭合：2 pass、1 fail、1 unknown，另1调用在途。该unknown确为HTTP200、`finish_reason=length`，completion为131072，其中reasoning为131067；端点报告了超过65536的用量，增加到131072仍不保证交付。不对此位置再次补抽，不改原基线。当前快照已知222,118 tokens不是在途调用的完整成本；报告哈希为 `4f33236721d5016c144bf726eac027b9402161ca034ee62ed9b1d5d7f49c08fa`，截断位置回执为 `05ed4910b1add851b5a413c9afe29325d9a3203919084a964839a507f007c0d9`。SSH随后因本机网络变化再次中断；已通过系统管理员授权恢复VPN单公网入口的临时直连路由，没有关闭或修改Clash，但SSH仍在认证前被关闭，等待核实aTrust登录/会话。后台进程不依赖本机，未经重新读取回执不能宣称远端已完成。

恢复连接后先读取原输出目录，不重新启动或重复提交：KOR为 `/root/continual-unknown-repair-20261001-kor-length`，Sheet v7为 `/root/continual-unknown-sheet-v7-20261002-replay`。两者均有意图/终态防重复保护；仅当旧进程不存在、回执无未决冲突且确有未提交位置时，才考虑原协议resume。完整重评结果须保留旧已知转unknown及分数翻转，不能只汇报覆盖增加。

原完整五域 No-Skill 分数不变，当前工作属于交付和评分环境修复，不是 Skill 进化或泛化效果。[原完整基线](results/noskill-fivebench-long-20261001.json) · [10/1诊断结果](unknown-recovery-20261001.md)
