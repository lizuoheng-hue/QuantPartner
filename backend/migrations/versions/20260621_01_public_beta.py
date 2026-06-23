"""public beta account, workspace, audit and paper trading baseline"""

from alembic import op
import sqlalchemy as sa

revision = "20260621_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 首个正式迁移面向全新的公测 PostgreSQL；现有本地 SQLite 由兼容迁移保留。
    from app.db import Base
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    # 公测数据包含审计与订单记录，禁止自动破坏性回滚。
    pass
