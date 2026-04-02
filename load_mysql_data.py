import os

import pymysql
from typing import Optional

# test 1

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
      - chain_id BIGINT NOT NULL        -- 链标识，这里统一为 0
      - next_id BIGINT NULL             -- 指向下一个节点的 id，对应 :NEXT 关系

    并插入一条长度为 node_count 的单链：
      (0)->(1)->(2)->...->(node_count-1)

    每次调用前会先删除并重新创建整个数据库，确保数据是干净的。
    """
    # 先连接到系统库，删除并重新创建数据库
    with get_mysql_connection() as conn, conn.cursor() as cur:
        cur.execute(f"DROP DATABASE IF EXISTS {MYSQL_DB}")
        cur.execute(
            f"CREATE DATABASE {MYSQL_DB} "
            "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
        )

    # 再连接到目标库，建表并插入数据（库此时为空）
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


def main() -> None:
    node_count = int(os.getenv("NODE_COUNT", "50000"))
    print(f"Preparing MySQL chain with {node_count} nodes in database '{MYSQL_DB}' ...")
    setup_mysql_schema_and_data(node_count=node_count)
    print("Done.")


if __name__ == "__main__":
    main()

