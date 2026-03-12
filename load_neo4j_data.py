import os
from typing import Optional

import pymysql
from neo4j import GraphDatabase


URI = os.getenv("NEO4J_URI", "neo4j://localhost:7687")
USER = os.getenv("NEO4J_USER", "neo4j")
PASSWORD = os.getenv("NEO4J_PASSWORD", "test")

MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_USER = os.getenv("MYSQL_USER", "root")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
MYSQL_DB = os.getenv("MYSQL_DB", "graph_benchmark")


def get_mysql_connection(db: Optional[str] = None):
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


def mirror_chain_from_mysql(driver) -> None:
    """
    从 MySQL 的 nodes 表中读取链表数据，完整镜像到 Neo4j：

    - MySQL: nodes(id, chain_id, next_id)
    - Neo4j: (:Node {id, chain_id}) 和 :NEXT 关系

    要求：先运行 load_mysql_data.py，保证 MySQL 中已有最新数据。
    """
    # 读出所有节点与边
    with get_mysql_connection(MYSQL_DB) as conn, conn.cursor() as cur:
        cur.execute("SELECT id, chain_id, next_id FROM nodes ORDER BY id")
        rows = cur.fetchall()

    with driver.session() as session:
        # 清空整图库，保证与 MySQL 完全一致
        session.run("MATCH (n) DETACH DELETE n")

        # 创建节点
        node_records = [(r[0], r[1]) for r in rows]
        session.run(
            """
            UNWIND $nodes AS n
            CREATE (:Node {id: n[0], chain_id: n[1]})
            """,
            nodes=node_records,
        )

        # 创建 NEXT 关系
        rels = [(r[0], r[2]) for r in rows if r[2] is not None]
        if rels:
            batch_size = 2000
            for offset in range(0, len(rels), batch_size):
                batch = rels[offset : offset + batch_size]
                session.run(
                    """
                    UNWIND $rels AS r
                    MATCH (a:Node {id: r[0]}), (b:Node {id: r[1]})
                    MERGE (a)-[:NEXT]->(b)
                    """,
                    rels=batch,
                )


def main() -> None:
    driver = GraphDatabase.driver(URI, auth=(USER, PASSWORD))
    try:
        print(f"Mirroring chain data from MySQL database '{MYSQL_DB}' into Neo4j ...")
        mirror_chain_from_mysql(driver)
        print("Done.")
    finally:
        driver.close()


if __name__ == "__main__":
    main()

