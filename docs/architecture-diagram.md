# Agent Workspace 架构图

> 面向非开发人员的 Agent 协作平台 · 上层封装 + 用户初始化 + 权限控制 + 多 Agent 协作

---

## 目录

1. [整体架构](#1-整体架构)
2. [用户初始化流程](#2-用户初始化流程)
3. [身份认证与权限控制](#3-身份认证与权限控制)
4. [Agent 协作层](#4-agent-协作层)
5. [CI / CD 与运行时](#5-ci--cd-与运行时)
6. [权限控制矩阵](#6-权限控制矩阵)
7. [关键角色说明](#7-关键角色说明)

---

## 1. 整体架构

```mermaid
flowchart TB
    U["<b>非开发人员</b><br/>业务 · 产品 · 运营 · 管理者"]

    U --> WB

    subgraph PRODUCT["上层封装"]
        WB["<b>统一工作台</b><br/>对话式需求入口 · 进度看板 · 结果交付<br/>无需 Git / K8s 知识 · 平台代管全流程"]
    end

    WB -->|"首次进入"| INIT

    subgraph INIT["用户初始化（首次使用，平台自动编排）"]
        direction LR
        I1["STEP 01<br/>账号开通<br/>SSO / 邀请制"]
        I2["STEP 02<br/>角色分配<br/>业务 / 产品 / 运营"]
        I3["STEP 03<br/>创建工作空间<br/>项目级隔离"]
        I4["STEP 04<br/>选择项目模板<br/>预置需求流程"]
        I5["STEP 05<br/>Agent 自动装配<br/>BA / Dev / QA / Deploy"]
        I6["STEP 06<br/>环境就绪<br/>可提交首个需求"]
        I1 --> I2 --> I3 --> I4 --> I5 --> I6
    end

    INIT -->|"已初始化"| AUTH

    subgraph SEC["安全准入"]
        AUTH["<b>身份认证与权限控制</b><br/>GitLab SSO · 分支保护 · MR 审批<br/>K8s RBAC · ACR 密钥 · Traefik TLS"]
    end

    AUTH -->|"已授权"| BA

    subgraph AGENT["Agent 协作层"]
        direction TB
        BA["<b>BA Agent</b><br/>需求 · 调度 · 状态机"]
        DM["<b>需求管理 · demand 分支</b><br/>需求文档 · 验收标准 · status.md"]
        BA --> DM

        DM --> DEV["<b>Dev Agent</b><br/>编码 · 测试 · PR"]
        DM --> QA["<b>QA Agent</b><br/>审查 · 验证 · 报告"]
        DM --> DEP["<b>Deploy Agent</b><br/>Kustomize · 发布"]
        DM --> EXP["<b>Explore Agent</b><br/>只读 · 调研 · 摸底"]

        DEV --> O1["feature/REQ-xxx<br/>独立 worktree"]
        QA --> O2["测试用例 / 验证报告<br/>BA/demands/REQ-xxx/"]
        DEP --> O3["deploy 分支<br/>overlays/uat · Ingress"]
        EXP --> O4["调研报告<br/>path:line 级证据"]
    end

    O1 --> CI
    O3 --> ARGO

    subgraph DELIVERY["CI / CD 与运行时"]
        direction TB
        CI["<b>CI 流水线</b><br/>build → test → docker build"]
        ACR[("<b>ACR 镜像仓库</b><br/>aigccontainer.azurecr.cn")]
        ARGO["<b>ArgoCD</b><br/>App-of-Apps · selfHeal"]
        K8S["<b>K8s 命名空间 × 5</b><br/>open-man · fde · gateway · aisearch · wb365"]
        TF["<b>Traefik Ingress</b><br/>通配 TLS · 自动发现"]
        POD["<b>业务 Pod</b><br/>Deployment 滚动更新"]

        CI --> ACR
        CI -.->|"写入 deploy 分支镜像 tag"| ARGO
        ACR -.->|"镜像拉取"| ARGO
        ARGO --> K8S --> TF --> POD
    end

    EXT["<b>外部用户</b><br/>*.local.anspire.cn"]
    EXT -->|"HTTPS"| TF
```

---

## 2. 用户初始化流程

非开发人员首次使用平台时，由平台自动编排六步初始化，用户无需接触任何 Git / K8s 操作。

```mermaid
flowchart LR
    S1["<b>STEP 01</b><br/>账号开通<br/><br/>SSO / 邀请制<br/>企业身份对接"]
    S2["<b>STEP 02</b><br/>角色分配<br/><br/>业务 / 产品 / 运营<br/>按角色授权"]
    S3["<b>STEP 03</b><br/>创建工作空间<br/><br/>项目级隔离<br/>独立 Git 仓库"]
    S4["<b>STEP 04</b><br/>选择项目模板<br/><br/>预置需求流程<br/>技术栈配置"]
    S5["<b>STEP 05</b><br/>Agent 自动装配<br/><br/>BA / Dev / QA / Deploy<br/>Worktree 初始化"]
    S6["<b>STEP 06</b><br/>环境就绪<br/><br/>工作台入口开放<br/>可提交首个需求"]

    S1 --> S2 --> S3 --> S4 --> S5 --> S6
```

### 步骤说明

| 步骤 | 动作 | 平台行为 | 用户感知 |
|------|------|---------|---------|
| 01 | 账号开通 | 对接企业 SSO 或发送邀请 | 登录工作台 |
| 02 | 角色分配 | 按角色授予不同项目访问范围 | 看到自己的工作区 |
| 03 | 创建工作空间 | 创建独立 Git 仓库 + 隔离命名空间 | 获得一个项目空间 |
| 04 | 选择项目模板 | 注入预置需求流程与技术栈配置 | 选择业务类型即可 |
| 05 | Agent 自动装配 | 拉起 BA / Dev / QA / Deploy 角色，初始化 worktree | 无需操作，后台完成 |
| 06 | 环境就绪 | 开放工作台入口 | 可以提第一个需求 |

---

## 3. 身份认证与权限控制

初始化完成后，所有操作经过统一的安全准入层。

```mermaid
flowchart LR
    U["非开发人员"] --> SSO["GitLab SSO<br/>企业身份"]
    SSO --> AUTHZ{"权限校验"}
    AUTHZ -->|"通过"| BA["BA Agent"]
    AUTHZ -->|"拒绝"| DENY["拒绝访问"]

    subgraph CHECKS["校验维度"]
        direction TB
        C1["项目成员身份"]
        C2["角色权限范围"]
        C3["分支 / 环境访问权"]
    end

    AUTHZ -.-> CHECKS
```

### 各组件权限点

| 组件 | 控制手段 |
|------|---------|
| **GitLab** | 分支保护 · MR 审批 · CODEOWNERS |
| **Kubernetes** | RBAC · ServiceAccount · NetworkPolicy |
| **ACR** | 拉取密钥（`azurecr-pull`）· 推送权限 |
| **Traefik** | 通配 TLS · 认证中间件 · 路由隔离 |
| **ArgoCD** | Project 隔离 · sync 权限 · 仓库凭据 |

---

## 4. Agent 协作层

### 4.1 角色分工

```mermaid
flowchart TB
    BA["<b>BA Agent</b><br/>需求 · 调度 · 状态机"]
    DM["<b>demand 分支</b><br/>需求文档 · 验收标准 · status.md"]

    BA --> DM

    DM --> DEV["<b>Dev Agent</b><br/>编码 · 测试 · PR"]
    DM --> QA["<b>QA Agent</b><br/>审查 · 验证 · 报告"]
    DM --> DEP["<b>Deploy Agent</b><br/>Kustomize · 发布"]
    DM --> EXP["<b>Explore Agent</b><br/>只读 · 调研 · 摸底"]

    DEV --> O1["feature/REQ-xxx<br/>独立 worktree"]
    QA --> O2["测试用例 / 验证报告"]
    DEP --> O3["deploy 分支<br/>overlays/uat · Ingress"]
    EXP --> O4["调研报告<br/>path:line 级证据"]
```

| 角色 | 职责 | 产出 | 写入权限 |
|------|------|------|---------|
| **BA Agent** | 需求拆解、任务调度、状态机唯一更新者 | 需求文档、验收标准、status.md | `demand` 分支 |
| **Dev Agent** | 编码实现、单元/集成测试、创建 PR | 源码、测试、追溯性矩阵 | `feature/REQ-xxx` |
| **QA Agent** | 代码审查、验证、出具报告 | 测试用例、验证报告 | 只读，报告给 BA |
| **Deploy Agent** | Kustomize 配置、镜像 tag、Ingress | 部署配置、发布记录 | `deploy` 分支 |
| **Explore Agent** | 代码调研、风险识别 | path:line 级调研报告 | 只读 |

### 4.2 需求状态机

```mermaid
stateDiagram-v2
    [*] --> 草稿
    草稿 --> 已评审
    已评审 --> 已就绪
    已就绪 --> 进行中
    进行中 --> 待验证
    进行中 --> 已取消
    待验证 --> 已验证
    待验证 --> 已退回
    已退回 --> 进行中
    已验证 --> 已完成
    已完成 --> [*]
```

**状态更新权归 BA 独占**：Dev 完成只通知 BA，QA 审核只报告 BA。

---

## 5. CI / CD 与运行时

```mermaid
flowchart TB
    subgraph CI_STAGE["CI — GitLab Runner"]
        direction LR
        B1["build"] --> B2["test"] --> B3["docker build"] --> B4["push 镜像"]
    end

    ACR[("<b>ACR 镜像仓库</b><br/>aigccontainer.azurecr.cn")]

    subgraph CD_STAGE["CD — ArgoCD"]
        direction LR
        A1["Bootstrap App<br/>5 个"] --> A2["业务 Application<br/>8 个"] --> A3["Kustomize 渲染"]
    end

    subgraph RUNTIME["K8s 运行时"]
        direction LR
        K1["anspire-open-man"]
        K2["anspire-fde-uat"]
        K3["anspire-gateway-uat"]
        K4["anspire-aisearch"]
        K5["anspire-wb365-bridge-uat"]
    end

    subgraph TRAFFIC["流量入口"]
        direction LR
        T1["Traefik Ingress<br/>通配 TLS"] --> T2["业务 Pod"]
    end

    B4 --> ACR
    B4 -.->|"写入 deploy 分支镜像 tag"| A1
    ACR -.->|"镜像拉取"| A1
    A3 --> RUNTIME
    RUNTIME --> TRAFFIC

    EXT["外部用户<br/>*.local.anspire.cn"] -->|"HTTPS"| T1
```

### 关键规范

| 维度 | 规范 |
|------|------|
| 镜像 tag | `aigccontainer.azurecr.cn/<service>:uat-YYYYMMDD-N` |
| 命名空间 | `<project>-<env>`，如 `anspire-fde-uat` |
| 域名 | `api-<service>-<env>.local.anspire.cn` |
| 同步策略 | `selfHeal: true` · `prune: false` · `ApplyOutOfSyncOnly` |
| IngressClass | `traefik` + 通配证书 `wildcard-local-anspire-cn` |

> `deploy` 分支**不参与构建**。CI 只产出镜像，CD 只消费镜像 tag。

---

## 6. 权限控制矩阵

| 组件 | 控制手段 | 作用范围 |
|------|---------|---------|
| **GitLab** | 分支保护 · MR 审批 · CODEOWNERS | 防止误改主干、强制代码评审 |
| **Kubernetes** | RBAC · ServiceAccount · NetworkPolicy | 命名空间级隔离、Pod 网络策略 |
| **ACR** | 拉取密钥（`azurecr-pull`）· 推送权限 | 镜像拉取鉴权、构建推送控制 |
| **Traefik** | 通配 TLS · 认证中间件 · 路由隔离 | HTTPS 终止、访问认证 |
| **ArgoCD** | Project 隔离 · sync 权限 · 仓库凭据 | 应用级隔离、部署权限 |

### 权限层级

```mermaid
flowchart TB
    L1["<b>平台管理员</b><br/>全部项目 · 全部环境"]
    L2["<b>项目负责人</b><br/>单项目 · 生产发布审批"]
    L3["<b>业务用户</b><br/>单项目 · 提交需求 · 查看进度"]
    L4["<b>外部用户</b><br/>仅访问已发布服务"]

    L1 --> L2 --> L3
    L3 -.->|"无平台权限"| L4
```

---

## 7. 关键角色说明

### 非开发人员视角

| 场景 | 传统方式 | 本平台 |
|------|---------|--------|
| 提需求 | 写文档、开会、邮件 | 在工作台对话式描述 |
| 看进度 | 问开发、查 Jira | 实时进度看板 |
| 验收结果 | 等测试报告 | 结果交付物直接可见 |
| 环境准备 | 提 IT 工单 | 初始化流程自动完成 |

### 技术底座视角

平台对非开发人员隐藏了以下复杂度：

- **Git 分支模型**：`workspace` / `demand` / `deploy` / `develop` / `feature` 五类分支
- **Worktree 隔离**：每个需求独立 worktree，互不干扰
- **多 Agent 协作**：BA 统一调度，Dev / QA / Deploy / Explore 分工执行
- **CI/CD 链路**：GitLab Runner 构建 → ACR 镜像 → ArgoCD 同步 → K8s 滚动更新
- **Ingress 注册**：Ingress 资源声明即自动注册到 Traefik，无需手工配置
