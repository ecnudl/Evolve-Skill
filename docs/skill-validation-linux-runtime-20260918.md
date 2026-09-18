# Linux 隔离执行环境准备记录（2026-09-18）

状态：官方 Python 镜像已加载；在受限 Docker 容器中实际执行 `python --version` 成功，返回 **Python 3.11.16**。这是运行环境工程检查，不是 Skill、Research 或 benchmark 效果实验；完整主线 smoke 结果另行报告。

## 环境与来源

- 开发机：`ssh PJ-CL4MIND-DULIN`，Linux x86_64。
- Docker：26.1.3，overlay2，数据目录 `/data/docker`。
- 独立下载工具环境：`/root/miniconda3/envs/skill_image_tools`，skopeo 1.24.0、containers-common 0.64.2；未给 `base` 或 `skill_validation` 添加包。
- 官方镜像：`docker.io/library/python:3.11-slim`，本次解析为 `3.11.16-slim-trixie`、linux/amd64。
- 没有修改 Docker daemon、系统代理或 Clash 配置，没有使用镜像站，也未关闭 TLS 校验或上传 API 密钥。

| 对象 | 固定摘要 |
| --- | --- |
| 官方多平台索引 | `sha256:9534e5a8e315485d4061ed659af0fd78a284c015f9b73661b41d6bab25604534` |
| 官方 linux/amd64 manifest | `sha256:d1053354624536b044162aaab1e418bd000ea35184fb1ae098ab3166b1072e72` |
| manifest 的 config／加载后的 Image ID | `sha256:b8fe4ce3655e95f7f22c2a87d8e03a2f1f0cedc488a8e9adf18cc5a18cfdf401` |
| 本地 Docker archive 文件 | `sha256:bab66161474d9bcd48df0a707446cac01a0bbc47f9f5305cfe6f872b05831fe8` |

镜像经 archive 导入，`RepoDigests=[]` 是本次实际结果，不伪造 repo digest。执行器应固定使用上表 **Image ID**，而不是可变的 `python:3.11-slim` 标签。加载后核对了 config digest、OS、架构及空的 `Config.Volumes`。这条来源链依赖官方 HTTPS registry 与内容摘要核对，不宣称已验证签名。

## 遇到的问题与处理

`proxy_on` 只在远端交互 Bash 初始化后可用。Shell HTTP 客户端启用它后请求官方 registry 得到正常的未认证状态 `401`，但 `docker pull` 由 daemon 发起，请求超时。

没有改 daemon 代理；改用受 shell 代理影响的 skopeo 下载，再由 Docker 加载本地 archive。conda-forge 此次组合携带 v1 `registries.conf`，而 skopeo 要求 v2；仅替换新工具环境中的该配置，使用以下内容：

```toml
unqualified-search-registries = ["docker.io"]
short-name-mode = "enforcing"
```

原配置保存在工具环境的 `registries.conf.packaged-v1`。最终环境配置是独立 inode；共享 conda 包缓存保持原配置，其 SHA256 与备份均为 `67b2fb33ce415577d249a28fe4e4aa495c5477538f1f4160d753bddfd1c0c4c0`。因此后续重建环境时还需注意这个工具包配置兼容性问题。

## 实际使用的关键命令

以下命令在远端执行；先进入交互 Bash 并运行 `proxy_on`。archive 已存在，不应重复覆盖。

```bash
conda create -n skill_image_tools --override-channels -c conda-forge skopeo -y --quiet

/root/miniconda3/envs/skill_image_tools/bin/skopeo \
  --command-timeout 45s --override-os linux --override-arch amd64 \
  inspect --no-creds --no-tags --format '{{.Digest}} {{.Architecture}} {{.Os}}' \
  docker://docker.io/library/python:3.11-slim

/root/miniconda3/envs/skill_image_tools/bin/skopeo \
  --command-timeout 280s \
  --policy /root/miniconda3/envs/skill_image_tools/etc/containers/policy.json \
  copy --src-no-creds \
  --digestfile /root/Evolve-Skill-validation/outputs/runtime_images/python311-copy.digest \
  docker://docker.io/library/python@sha256:d1053354624536b044162aaab1e418bd000ea35184fb1ae098ab3166b1072e72 \
  docker-archive:/root/Evolve-Skill-validation/outputs/runtime_images/python311.tar:python:3.11-slim

docker load --input /root/Evolve-Skill-validation/outputs/runtime_images/python311.tar
docker image inspect python:3.11-slim \
  --format 'id={{.Id}} repo_digests={{json .RepoDigests}} os={{.Os}} arch={{.Architecture}} size={{.Size}} volumes={{json .Config.Volumes}}'
```

实际 readiness 容器启用了：固定 Image ID、`--pull=never`、`--network=none`、只读根文件系统、UID/GID 65534、移除全部 capabilities、no-new-privileges、64 PID、256 MiB 内存及相同 swap 总上限、1 CPU、无 IPC、16 MiB 有限 tmpfs、无 Docker 日志写入。命令仅执行镜像自身的 `python --version`；未挂载仓库、凭证或 Docker socket。运行完成后按精确容器名确认容器已不存在。

## 磁盘与验收边界

测得新增相关组件约 **326 MiB**：工具环境 39,895,040 B、archive 目录 137,646,080 B、Docker overlay 145,948,672 B、工具 conda 下载包 18,128,896 B。Docker 报告镜像逻辑大小 133,023,775 B。以上不是严密的整机前后差分；未计入共享 conda repodata 的新增量，也不能把硬链接文件简单重复累加。

这一步只消除了运行时镜像的前置阻碍。Docker 隔离不等于对恶意候选的测量防篡改保证；当前 callable observer 与候选共享 Python 进程。下一步应运行并保存主线真实容器 fixture 回执，验证状态快照、异常、超时、清理及离线回放，再讨论模型产物实验。
