from types import SimpleNamespace
import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from web.api.members import create_member, update_member
from web.db_models import Member
from web.schemas import MemberCreate, MemberUpdate


class MembersApiTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        Member.__table__.create(self.engine)
        self.session = Session(self.engine)
        self.user = SimpleNamespace(id=1)

    def tearDown(self):
        self.session.close()
        self.engine.dispose()

    def test_outsourced_status_is_inferred_and_can_be_overridden(self):
        member = create_member(
            MemberCreate(real_name="v_alice(艾丽丝)", git_name="v_alice"),
            self.session,
            self.user,
        )
        self.assertTrue(member.is_outsourced)

        updated = update_member(
            member.id,
            MemberUpdate(is_outsourced=False),
            self.session,
            self.user,
        )
        self.assertFalse(updated.is_outsourced)


if __name__ == "__main__":
    unittest.main()
