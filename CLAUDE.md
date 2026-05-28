# 多 Agent 协同协议（设计中台项目）

本仓库按「角色」切分文件夹。每个 Claude Code 窗口扎根一个角色文件夹 = 一个独立 agent。
本文件是所有角色共享的协作契约——它会被各角色窗口自动加载（因为它是各角色文件夹的父目录）。

## 一、角色拓扑

主动角色（一窗口一 agent，各有 CLAUDE.md 身份卡）：

| 文件夹 | 角色 |
|---|---|
| image-prd/    | 产品经理（PM） |
| image-code/   | 开发（Dev） |
| image-qa/     | 测试（QA） |
| image-market/ | 调研（Research） |
| image-ops/    | 运维（Ops） |

共享黑板（无 agent 常驻，多角色读写）：

| 文件夹 | 用途 |
|---|---|
| image-issues/ | 问题 / Bug 记录，一问题一文件 |

## 二、写入边界（铁律）

**每个角色只写自己的主文件夹 + image-issues 黑板。绝不直接修改其他角色的主文件夹。**
需要别的角色改东西 → 在 image-issues 开一条记录，把 owner 指给对方。

| 角色 | 可写 | 只读 |
|---|---|---|
| PM   | image-prd/    + issues | market / qa / code |
| 开发 | image-code/   + issues | prd / qa / issues |
| QA   | image-qa/     + issues | prd / code / issues |
| 调研 | image-market/ + issues | — |
| 运维 | image-ops/    + issues | code / issues |

## 三、image-issues 黑板规约

- 一个问题一个文件：`ISSUE-{4位编号}-{短描述}.md`，编号全局递增（如 `ISSUE-0001-sse-断连.md`）。
- 复制 `image-issues/_TEMPLATE.md` 开新问题。
- 状态机：
  `待复现 → 已确认 → 修复中 → 待验证 → 已修复 → 已关闭`
  分支：`无法复现 → 已关闭`；任意态 → `挂起`。
- `owner` 字段 = 球当前在谁手里（负责推进的角色）。**改状态时同步改 owner。**
- 每次改动在「处理记录」追加一行：`日期 [角色] 动作`。
- 严重度：P0 阻断 / P1 严重 / P2 一般 / P3 轻微。

典型流转：
开发写 bug(待复现, owner=QA) → QA 复现(已确认, owner=开发) → 开发修(修复中→待验证, owner=QA) → QA 验(已修复→已关闭)

## 四、启动各角色窗口

在项目根目录下，每个窗口这样开（`--add-dir` 挂载该角色需要读的文件夹）：

- PM：   `cd image-prd    && claude --add-dir ../image-market --add-dir ../image-issues --add-dir ../image-qa`
- 开发： `cd image-code   && claude --add-dir ../image-prd --add-dir ../image-issues --add-dir ../image-qa`
- QA：   `cd image-qa     && claude --add-dir ../image-prd --add-dir ../image-code --add-dir ../image-issues`
- 调研： `cd image-market && claude`
- 运维： `cd image-ops    && claude --add-dir ../image-code --add-dir ../image-issues`
