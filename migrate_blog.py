from common.database import engine
from sqlalchemy import text

def run():
    with engine.connect() as conn:
        try:
            conn.execute(text("ALTER TABLE blog_posts ADD COLUMN tags TEXT DEFAULT '[]'"))
        except Exception as e:
            print("tags:", e)
        try:
            conn.execute(text("ALTER TABLE blog_posts ADD COLUMN views_count INTEGER DEFAULT 0"))
        except Exception as e:
            print("views_count:", e)
        try:
            conn.execute(text("ALTER TABLE blog_posts ADD COLUMN likes_count INTEGER DEFAULT 0"))
        except Exception as e:
            print("likes_count:", e)
        try:
            conn.execute(text("ALTER TABLE blog_posts ADD COLUMN dislikes_count INTEGER DEFAULT 0"))
        except Exception as e:
            print("dislikes_count:", e)
        conn.commit()

if __name__ == "__main__":
    run()
