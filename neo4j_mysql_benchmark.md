### 一、对比基准脚本概览

- **依赖文件 `requirements.txt`**
  ```text
  neo4j>=5.25.0
  pytest>=8.0.0
  pymysql>=1.1.0
  ```

- **`neo_benchmark.py` 概要**
  - **Neo4j 部分**
    - 使用环境变量或默认值连接：
      - `NEO4J_URI`（默认 `neo4j://localhost:7687`）
      - `NEO4J_USER`（默认 `neo4j`）
      - `NEO4J_PASSWORD`（默认 `test`）
    - `setup_sample_graph(driver, node_count=500_000)`：
      - 在 Neo4j 中构建一条长度为 500,000 的单链：
        \(:Node {id: 0})-[:NEXT]->(:Node {id: 1})-[:NEXT]->...-[:NEXT]->(:Node {id: 499999})
    - `benchmark_traversal(driver, start_id=0, depth=5, runs=500)`：
      - 从 `id=0` 出发，沿 `:NEXT` 关系走 5 跳，重复 500 次，统计平均单次耗时（毫秒）。
  - **MySQL 部分**
    - 使用环境变量或默认值连接：
      - `MYSQL_HOST`（默认 `localhost`）
      - `MYSQL_PORT`（默认 `3306`）
      - `MYSQL_USER`（默认 `root`）
      - `MYSQL_PASSWORD`（默认空）
      - `MYSQL_DB`（默认 `graph_benchmark`）
    - `setup_mysql_schema_and_data(node_count=500_000)`：
      - 自动创建数据库 `graph_benchmark`
      - 建表 `nodes` 并插入 500,000 行链表数据
    - `benchmark_mysql_traversal(depth=5, runs=500)`：
      - 用一个包含 5 次自连接的 SQL，从随机起点沿链表走 5 跳，重复 500 次，统计平均单次耗时（毫秒）。
  - **运行入口 `run_benchmarks()`**
    - 顺序执行：
      - Neo4j 准备数据 + 深度遍历基准
      - MySQL 准备数据 + 5 层自连接基准
    - 控制台打印类似：
      ```text
      [Neo4j] depth=5, runs=500, avg=... ms, hops=5
      [MySQL] depth=5, runs=500, avg=... ms
      ```

---

### 二、Neo4j 与 MySQL 等价数据模型

#### 1. 语义目标

- **数据结构**：一条长链表（单链图）
  \[
  0 \rightarrow 1 \rightarrow 2 \rightarrow \dots \rightarrow (N-1)
  \]
- **等价要求**：
  - Neo4j 和 MySQL 表示同一条有向链；
  - 查询的问题：从某个起点出发，沿链表向前走固定 5 步。

#### 2. Neo4j 中的数据建模

- **节点标签/属性**
  - 节点类型：`Node`
  - 节点属性：
    - `id: INTEGER` — 节点编号（0 到 N-1）
    - `chain_id: INTEGER` — 链编号，这里统一为 0

- **关系类型**
  - 关系类型：`NEXT`
  - 方向：`(a:Node)-[:NEXT]->(b:Node)`
  - 语义：
    - 若存在 `(:Node {id: i})-[:NEXT]->(:Node {id: j})`，表示“链表中 i 的下一个节点是 j”。

- **数据示例（N=10）**
  - 节点：
    - `(:Node {id: 0, chain_id: 0})`
    - ...
    - `(:Node {id: 9, chain_id: 0})`
  - 关系：
    - `(0)-[:NEXT]->(1)`
    - ...
    - `(8)-[:NEXT]->(9)`
    - `9` 无 `NEXT` 出边。

#### 3. MySQL 中的等价表结构

- **表名**：`nodes`

- **字段设计**
  ```sql
  CREATE TABLE nodes (
    id       BIGINT PRIMARY KEY,  -- 对应 Neo4j 中 Node.id
    chain_id BIGINT NOT NULL,     -- 对应 Neo4j 中 Node.chain_id
    next_id  BIGINT NULL,         -- 指向“下一个节点”的 id，对应 :NEXT 关系
    KEY idx_chain_id (chain_id),
    KEY idx_next_id (next_id)
  ) ENGINE=InnoDB;
  ```

- **数据示例（N=10）**

  | id | chain_id | next_id |
  |----|----------|--------:|
  | 0  | 0        | 1       |
  | 1  | 0        | 2       |
  | 2  | 0        | 3       |
  | 3  | 0        | 4       |
  | 4  | 0        | 5       |
  | 5  | 0        | 6       |
  | 6  | 0        | 7       |
  | 7  | 0        | 8       |
  | 8  | 0        | 9       |
  | 9  | 0        | NULL    |

对应关系：

- `nodes.id` ↔ `Node.id`
- `nodes.chain_id` ↔ `Node.chain_id`
- `nodes.next_id` ↔ `(:Node {id})-[:NEXT]->(:Node {next_id})`

---

### 三、等价查询问题定义（Neo4j vs MySQL）

#### 1. 业务问题

- 问题：给定起始节点 `start_id`，沿链表向前走 5 步，找到第 5 个节点。
- 形式化：
  \[
  n_0.id = start\_id,\quad n_{k+1}.id = n_k.next\_id,\quad k=0,\dots,3
  \]
  目标是 `n_5.id`。

#### 2. Neo4j 查询（Cypher）

路径展开写法：

```cypher
MATCH p = (n:Node {id: $start_id})-[:NEXT*5]->(m:Node)
RETURN m.id AS target_id;
```

或逐跳写法：

```cypher
MATCH (n0:Node {id: $start_id})
MATCH (n0)-[:NEXT]->(n1:Node)
MATCH (n1)-[:NEXT]->(n2:Node)
MATCH (n2)-[:NEXT]->(n3:Node)
MATCH (n3)-[:NEXT]->(n4:Node)
MATCH (n4)-[:NEXT]->(n5:Node)
RETURN n5.id AS target_id;
```

#### 3. MySQL 查询（5 次自连接）

```sql
SELECT n5.id
FROM nodes AS n0
JOIN nodes AS n1 ON n1.id = n0.next_id
JOIN nodes AS n2 ON n2.id = n1.next_id
JOIN nodes AS n3 ON n3.id = n2.next_id
JOIN nodes AS n4 ON n4.id = n3.next_id
JOIN nodes AS n5 ON n5.id = n4.next_id
WHERE n0.id = ?;
```

语义等价于上面的 Cypher：都是“从起点沿 `NEXT`/`next_id` 走 5 步”。

---

### 四、为什么 MySQL 端设计成「总耗时 > 3 秒」

在 `benchmark_mysql_traversal` 中使用：

- `node_count = 500_000`（50 万节点的单链）
- `runs = 500`（执行 500 次 5 层自连接查询）

伪代码：

```python
for _ in range(500):
    start_id = random.randint(0, 400_000)
    执行一次 SELECT ... JOIN ...（5 层自连接）
    记录本次耗时
```

- 若单次查询平均耗时 5 ms，则总耗时约 2.5 s；
- 若单次查询平均耗时 10 ms，则总耗时约 5 s。

通过放大数据规模（50 万节点）和查询次数（500 次），在普通开发机上多数情况下：

- **MySQL 这段 benchmark 总耗时有较大概率超过 3 秒**；
- 同时 Neo4j 在相同规模和查询语义下通常有更小的平均耗时；
- 从而可以较明显地观察到两者在“深度关系遍历”场景下的性能差异。

