import os

from neo4j import GraphDatabase


URI = os.getenv("NEO4J_URI", "neo4j://localhost:7687")
USER = os.getenv("NEO4J_USER", "neo4j")
PASSWORD = os.getenv("NEO4J_PASSWORD", "test")


def setup_sample_graph(driver, node_count: int = 50_000) -> None:
    """
    在 Neo4j 中创建一条长度为 node_count 的单链：
      (:Node {id: 0})-[:NEXT]->(:Node {id: 1})-[:NEXT]->...-[:NEXT]->(:Node {id: node_count-1})
    """
    with driver.session() as session:
        session.run("MATCH (n) DETACH DELETE n")

        def create_batch(tx, offset, batch_size):
            query = """
            UNWIND range($offset, $offset + $batch_size - 1) AS i
            MERGE (n:Node {id: i, chain_id: 0})
            WITH collect(n) AS ns
            UNWIND range(0, size(ns) - 2) AS idx
            WITH ns[idx] AS a, ns[idx + 1] AS b
            MERGE (a)-[:NEXT]->(b)
            """
            tx.run(query, offset=offset, batch_size=batch_size)

        batch_size = 2000
        for offset in range(0, node_count, batch_size):
            session.execute_write(create_batch, offset, min(batch_size, node_count - offset))


def main() -> None:
    node_count = int(os.getenv("NODE_COUNT", "50000"))
    driver = GraphDatabase.driver(URI, auth=(USER, PASSWORD))
    try:
        print(f"Preparing Neo4j chain with {node_count} nodes ...")
        setup_sample_graph(driver, node_count=node_count)
        print("Done.")
    finally:
        driver.close()


if __name__ == "__main__":
    main()

