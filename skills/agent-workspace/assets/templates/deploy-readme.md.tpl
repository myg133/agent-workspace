# Deploy — 部署配置（`deploy` 分支）

本目录只放**部署配置**，不放业务代码、不做构建。集群状态必须能从这里重建。

## 目录

```text
apps/<svc>/base/                 kustomization + deployment/service/ingress
apps/<svc>/overlays/{uat,production}/   环境差异（镜像 tag、副本数、env）
argocd/applications/             bootstrap 扫描的 Application
argocd/bootstrap/                排除扫描
environments/                    跨应用环境配置
releases/                        发布快照（vX.Y.Z.yaml）
scripts/                         deploy / rollback / healthcheck
```

## 纪律

- 改生产 = 改 overlay 的镜像 tag + commit + push，不手动 `kubectl apply`。
- 每次发布写 `releases/vX.Y.Z.yaml`。
- 回滚也是提交（改回旧 tag），不是 `rollout undo`。
