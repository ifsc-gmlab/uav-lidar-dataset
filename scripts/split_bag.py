"""
Split a ROS1 bag into multiple parts, each under a target size.

Preserves raw message bytes (no re-serialization), so concatenating parts
with AnyReader([part0, part1, ...]) gives the exact original stream.

Usage:
    python scripts/split_bag.py bags/xxx.bag --max-size 1800
    python scripts/split_bag.py bags/xxx.bag --max-size 1800 --out-dir bags/split/
"""
import argparse
from pathlib import Path
from rosbags.rosbag1 import Reader, Writer


def split_bag(src: Path, out_dir: Path, max_size_mb: float):
    target_bytes = int(max_size_mb * 1024 * 1024)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"源文件: {src.name}  ({src.stat().st_size/1e6:.1f} MB)")
    print(f"目标分片大小: {max_size_mb} MB")

    reader = Reader(src)
    reader.open()

    part_idx = 0
    written = 0
    writer = None
    conn_map = {}  # original conn id -> new conn in current writer
    topic_map = {}  # topic name -> new conn (writer dedups by topic)

    def open_new_writer():
        nonlocal writer, conn_map, topic_map, written, part_idx
        if writer is not None:
            writer.close()
        part_idx += 1
        out_path = out_dir / f"{src.stem}_part{part_idx}.bag"
        writer = Writer(out_path)
        writer.open()
        conn_map = {}
        topic_map = {}
        written = 0
        print(f"  写入分片: {out_path.name}")

    def add_conn(conn):
        if conn.topic in topic_map:
            return topic_map[conn.topic]
        new_conn = writer.add_connection(
            conn.topic,
            conn.msgtype,
            msgdef=conn.msgdef.data,
            md5sum=conn.digest,
        )
        topic_map[conn.topic] = new_conn
        return new_conn

    open_new_writer()

    for conn, ts, raw in reader.messages():
        # Ensure this connection exists in current writer (keyed by original conn.id)
        if conn.id not in conn_map:
            conn_map[conn.id] = add_conn(conn)

        # If current part is full, roll over
        if written > 0 and written + len(raw) > target_bytes:
            open_new_writer()
            conn_map[conn.id] = add_conn(conn)

        new_conn = conn_map[conn.id]
        writer.write(new_conn, ts, raw)
        written += len(raw)

    if writer is not None:
        writer.close()
    reader.close()

    print(f"\n完成: 切成 {part_idx} 片")
    for f in sorted(out_dir.glob(f"{src.stem}_part*.bag")):
        print(f"  {f.name}  {f.stat().st_size/1e6:.1f} MB")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("bag", help="Source .bag file")
    ap.add_argument("--max-size", type=float, default=1800, help="Max MB per part (default 1800)")
    ap.add_argument("--out-dir", type=str, default=None, help="Output dir (default: same dir as source)")
    args = ap.parse_args()

    src = Path(args.bag).resolve()
    if not src.exists():
        raise SystemExit(f"Not found: {src}")

    out_dir = Path(args.out_dir).resolve() if args.out_dir else src.parent
    split_bag(src, out_dir, args.max_size)


if __name__ == "__main__":
    main()
