import os
import random
import time
from typing import Optional, Tuple

import pymysql
from neo4j import GraphDatabase


# Neo4j 配置
URI = os.getenv("NEO4J_URI", "neo4j://localhost:7687")
USER = os.getenv("NEO4J_USER", "neo4j")
PASSWORD = os.getenv("NEO4J_PASSWORD", "test")


def get_driver():
    return GraphDatabase.driver(URI, auth=(USER, PASSWORD))


def setup_sample_graph(driver, node_count: int = 50_000) -> None:
    """
    创建一个简单的单链图：
    (:Node {id: 0})-[:NEXT]->(:Node {id: 1})-[:NEXT]->...，直到 id=node_count-1。
    这样便于做深度遍历的简单基准测试。
    """
    with driver.session() as session:
        session.run("MATCH (n) DETACH DELETE n")

        def create_batch(tx, offset, batch_size):
            query = """
            UNWIND range($offset, $offset + $batch_size - 1) AS i
            MERGE (n:Node {id: i})
            WITH collect(n) AS ns
            UNWIND range(0, size(ns) - 2) AS idx
            WITH ns[idx] AS a, ns[idx + 1] AS b
            MERGE (a)-[:NEXT]->(b)
            """
            tx.run(query, offset=offset, batch_size=batch_size)

        batch_size = 200
        for offset in range(0, node_count, batch_size):
            session.execute_write(create_batch, offset, min(batch_size, node_count - offset))


def benchmark_traversal(driver, start_id: int, depth: int, runs: int = 50) -> Tuple[float, int]:
    """
    从给定起点出发，沿着 :NEXT 关系做固定深度的遍历，多次重复并统计耗时。
    返回 (平均耗时毫秒, 每次遍历访问到的节点数)。
    """
    cypher = """
    MATCH (n:Node {id: $start_id})
    CALL apoc.path.expandConfig(n, {
      relationshipFilter: 'NEXT>',
      minLevel: $depth,
      maxLevel: $depth
    }) YIELD path
    RETURN length(path) AS hops
    """

    with driver.session() as session:
        durations = []
        last_hops = 0
        for _ in range(runs):
            t0 = time.perf_counter()
            result = session.run(cypher, start_id=start_id, depth=depth)
            record = result.single()
            t1 = time.perf_counter()
            durations.append((t1 - t0) * 1000)
            last_hops = record["hops"] if record else 0

    avg_ms = sum(durations) / len(durations)
    return avg_ms, last_hops


########################
# MySQL 等价链表建模与基准
########################

MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_USER = os.getenv("MYSQL_USER", "root")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
MYSQL_DB = os.getenv("MYSQL_DB", "graph_benchmark")


def get_mysql_connection(db: Optional[str] = None):
    """
    获取 MySQL 连接。
    如果 db 为 None，则连接到默认系统库，用于创建数据库。
    """
    return pymysql.connect(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=db,
        autocommit=True,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.Cursor,
    )


def setup_mysql_schema_and_data(node_count: int = 50_000) -> None:
    """
    在 MySQL 中创建等价的数据模型：

    表 nodes:
      - id BIGINT PRIMARY KEY           -- 对应 Neo4j 中 :Node 的 id 属性
      - chain_id BIGINT NOT NULL        -- 链标识，这里统一为 0，方便扩展多链
      - next_id BIGINT NULL             -- 指向下一个节点的 id，对应 :NEXT 关系

    并插入一条长度为 node_count 的单链：
      (0)->(1)->(2)->...->(node_count-1)
    """
    # 先连接到系统库，创建数据库
    with get_mysql_connection() as conn, conn.cursor() as cur:
        cur.execute(f"CREATE DATABASE IF NOT EXISTS {MYSQL_DB} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")

    # 再连接到目标库，建表并插入数据
    with get_mysql_connection(MYSQL_DB) as conn, conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS nodes (
              id BIGINT PRIMARY KEY,
              chain_id BIGINT NOT NULL,
              next_id BIGINT NULL,
              KEY idx_chain_id (chain_id),
              KEY idx_next_id (next_id)
            ) ENGINE=InnoDB
            """
        )
        cur.execute("TRUNCATE TABLE nodes")

        batch_size = 10_000
        for offset in range(0, node_count, batch_size):
            rows = []
            upper = min(node_count, offset + batch_size)
            for i in range(offset, upper):
                next_id = i + 1 if i < node_count - 1 else None
                rows.append((i, 0, next_id))
            cur.executemany(
                "INSERT INTO nodes (id, chain_id, next_id) VALUES (%s, %s, %s)",
                rows,
            )


def benchmark_mysql_traversal(depth: int = 5, runs: int = 500) -> float:
    """
    在 MySQL 中做等价的“从随机起点沿链表走固定深度”的查询基准。
    查询形式为 5 次自连接：

      n0 JOIN n1 JOIN n2 JOIN n3 JOIN n4 JOIN n5

    为了让总执行时间尽量超过 3 秒，这里默认：
      - 节点数 node_count = 500_000
      - runs = 500（重复执行 500 次）

    返回：每次查询的平均耗时（毫秒）。
    """
    sql = """
    SELECT n5.id
    FROM nodes AS n0
    JOIN nodes AS n1 ON n1.id = n0.next_id
    JOIN nodes AS n2 ON n2.id = n1.next_id
    JOIN nodes AS n3 ON n3.id = n2.next_id
    JOIN nodes AS n4 ON n4.id = n3.next_id
    JOIN nodes AS n5 ON n5.id = n4.next_id
    WHERE n0.id = %s
    """

    with get_mysql_connection(MYSQL_DB) as conn, conn.cursor() as cur:
        durations: list[float] = []
        max_start = 400_000  # 留出足够空间保证能走完 5 跳
        for _ in range(runs):
            start_id = random.randint(0, max_start)
            t0 = time.perf_counter()
            cur.execute(sql, (start_id,))
            cur.fetchall()
            t1 = time.perf_counter()
            durations.append((t1 - t0) * 1000)

    avg_ms = sum(durations) / len(durations)
    return avg_ms


def run_benchmarks() -> None:
    depth = 5
    neo_runs = 500
    mysql_runs = 500

    print("=== Neo4j: 准备数据（50k 节点） ===")
    driver = get_driver()
    try:
        setup_sample_graph(driver, node_count=50_000)
        print("=== Neo4j: 深度遍历基准 ===")
        neo_avg_ms, hops = benchmark_traversal(driver, start_id=0, depth=depth, runs=neo_runs)
        print(f"[Neo4j] depth={depth}, runs={neo_runs}, avg={neo_avg_ms:.3f} ms, hops={hops}")
    finally:
        driver.close()

    print("=== MySQL: 准备数据（50k 节点） ===")
    setup_mysql_schema_and_data(node_count=50_000)
    print("=== MySQL: 深度遍历基准（多次 5 层自连接） ===")
    mysql_avg_ms = benchmark_mysql_traversal(depth=depth, runs=mysql_runs)
    print(f"[MySQL] depth={depth}, runs={mysql_runs}, avg={mysql_avg_ms:.3f} ms")


if __name__ == "__main__":
    run_benchmarks()
