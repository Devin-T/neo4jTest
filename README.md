### 项目简介

这个仓库用于对比 **Neo4j** 和 **MySQL** 在「深度关系遍历」场景下的性能差异，并提供：

- 构造等价数据的脚本（Neo4j / MySQL 各一份）
- 基准测试脚本 `neo_benchmark.py`
- 简单的 Neo4j 连通性测试（`pytest`）

---

### 环境准备

- Python 3.9+（推荐）
- 已安装并可连接的：
  - Neo4j（默认地址 `neo4j://localhost:7687`）
  - MySQL（默认地址 `localhost:3306`）

#### 1. 创建虚拟环境并安装依赖

```bash
cd /Users/tianye/code/neo4jTest
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

### 使用 `.env` 管理环境变量

项目根目录已经提供了一个示例 `.env` 文件，包含 Neo4j / MySQL 以及节点数量等配置：

```env
NEO4J_URI=neo4j://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=test

MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=
MYSQL_DB=graph_benchmark

NODE_COUNT=500000
```

你可以根据自己本地环境修改 `.env`，然后在运行脚本前让 shell 自动加载这些变量，例如：

```bash
cd /Users/tianye/code/neo4jTest
set -a           # 让当前 shell 自动导出变量
source .env      # 加载 .env 中的配置
set +a
```

之后再执行下面的各类脚本（插数、基准测试等），就会自动读取这些环境变量。

---

### 数据模型说明

详见 `neo4j_mysql_benchmark.md`，这里只简单回顾：

- 逻辑结构是一条长链表：
  \[
  0 \rightarrow 1 \rightarrow 2 \rightarrow \dots \rightarrow (N-1)
  \]
- Neo4j：
  - 节点：`(:Node {id, chain_id})`
  - 关系：`(a:Node)-[:NEXT]->(b:Node)`
- MySQL：
  - 表：`nodes(id BIGINT PRIMARY KEY, chain_id BIGINT, next_id BIGINT)`
  - 行：`(id=i, chain_id=0, next_id=i+1)`，尾节点 `next_id=NULL`。

---

### 一、向 Neo4j 插入测试数据

脚本：`load_neo4j_data.py`

**功能**：在 Neo4j 中创建一条长度为 `NODE_COUNT` 的单链，并清空原有数据。

- 默认配置（可通过环境变量覆盖）：
  - `NEO4J_URI`：默认 `neo4j://localhost:7687`
  - `NEO4J_USER`：默认 `neo4j`
  - `NEO4J_PASSWORD`：默认 `test`
  - `NODE_COUNT`：默认 `500000`（50 万节点）

**执行方法**：

```bash
cd /Users/tianye/code/neo4jTest
source .venv/bin/activate

# 如需修改节点数量，比如 100 万：
# export NODE_COUNT=1000000

python load_neo4j_data.py
```

执行完成后，Neo4j 中将存在：

```text
(:Node {id: 0, chain_id: 0})-[:NEXT]->(:Node {id: 1, chain_id: 0})->...->(:Node {id: NODE_COUNT-1, chain_id: 0})
```

---

### 二、向 MySQL 插入测试数据

脚本：`load_mysql_data.py`

**功能**：在 MySQL 中创建数据库和表，并插入等价的链式数据：

- 数据库：`graph_benchmark`（可通过 `MYSQL_DB` 环境变量修改）
- 表结构：`nodes(id BIGINT PRIMARY KEY, chain_id BIGINT, next_id BIGINT)`
- 数据：一条长度为 `NODE_COUNT` 的单链。

默认配置（可通过环境变量覆盖）：

- `MYSQL_HOST`：默认 `localhost`
- `MYSQL_PORT`：默认 `3306`
- `MYSQL_USER`：默认 `root`
- `MYSQL_PASSWORD`：默认空
- `MYSQL_DB`：默认 `graph_benchmark`
- `NODE_COUNT`：默认 `500000`

**执行方法**：

```bash
cd /Users/tianye/code/neo4jTest
source .venv/bin/activate

# 根据你本地 MySQL 情况设置环境变量（示例）：
# export MYSQL_HOST=localhost
# export MYSQL_PORT=3306
# export MYSQL_USER=root
# export MYSQL_PASSWORD=your_password
# export MYSQL_DB=graph_benchmark
# export NODE_COUNT=500000

python load_mysql_data.py
```

执行完成后，MySQL 中将有：

```text
nodes 表：
  id:       0..NODE_COUNT-1
  chain_id: 全部为 0
  next_id:  i < NODE_COUNT-1 时为 i+1，尾节点为 NULL
```

---

### 三、运行 Neo4j / MySQL 性能对比基准

脚本：`neo_benchmark.py`

**功能**：

- 如果需要，会在 Neo4j / MySQL 中构造同样的数据（与上面两个脚本一致）；
- 然后分别执行多次深度为 5 的遍历：
  - Neo4j：从起点沿 `:NEXT` 走 5 步；
  - MySQL：对 `nodes` 表执行 5 层自连接。

**执行方法**：

```bash
cd /Users/tianye/code/neo4jTest
source .venv/bin/activate

# 确保 Neo4j 服务和 MySQL 服务都已经启动，环境变量同上

python neo_benchmark.py
```

你会看到类似输出：

```text
[Neo4j] depth=5, runs=500, avg=... ms, hops=5
[MySQL] depth=5, runs=500, avg=... ms
```

---

### 四、Neo4j 连通性测试（可选）

使用 `pytest` 对 Neo4j 做最基本的连通性和读写校验：

```bash
cd /Users/tianye/code/neo4jTest
source .venv/bin/activate
pytest -q
```

要求 Neo4j 服务已启动，且账号密码与环境变量一致。

