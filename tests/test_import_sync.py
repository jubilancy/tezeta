"""The Firestore import writes only what changed. These tests use an in-memory stand-in for Firestore."""
import import_terms
from import_terms import BATCH, make_plan, sync


class Snap:
    def __init__(self, doc_id, data):
        self.id, self._data = doc_id, data

    def to_dict(self):
        return dict(self._data)


class Ref:
    def __init__(self, doc_id):
        self.id = doc_id


class QuotaExhausted(Exception):
    pass


QuotaExhausted.__name__ = "ResourceExhausted"  # the import recognises Google's error by name


class FakeStore:
    """A collection plus the client that batches writes to it, counting every write."""

    def __init__(self, existing=None, fail_commit_number=None):
        self.data = dict(existing or {})
        self.writes = 0
        self.deletes = 0
        self.commits = 0
        self.fail_commit_number = fail_commit_number

    def stream(self):
        return [Snap(k, v) for k, v in self.data.items()]

    def document(self, doc_id):
        return Ref(doc_id)

    def batch(self):
        return FakeBatch(self)


class FakeBatch:
    def __init__(self, store):
        self.store, self.ops = store, []

    def set(self, ref, doc):
        self.ops.append(("set", ref.id, doc))

    def delete(self, ref):
        self.ops.append(("delete", ref.id, None))

    def commit(self):
        s = self.store
        s.commits += 1
        if s.fail_commit_number == s.commits:
            raise QuotaExhausted("quota")
        assert len(self.ops) <= 500, "Firestore batches are limited to 500 operations"
        for op, doc_id, doc in self.ops:
            if op == "set":
                s.data[doc_id] = doc
                s.writes += 1
            else:
                s.data.pop(doc_id, None)
                s.deletes += 1


def docs_n(n, definition="d"):
    return {f"t{i}": {"term": f"t{i}", "definition": f"{definition}{i}", "vibe": "v"} for i in range(n)}


def run(store, docs, **kw):
    lines = []
    code = sync(store, store, docs, out=lines.append, **kw)
    return code, lines


def test_plan_classifies_new_changed_unchanged_stale():
    docs = {"a": {"term": "a", "definition": "1"}, "b": {"term": "b", "definition": "NEW"}, "c": {"term": "c", "definition": "3"}}
    existing = {"a": {"term": "a", "definition": "1"}, "b": {"term": "b", "definition": "old"}, "z": {"term": "z", "definition": "9"}}
    plan = make_plan(docs, existing)
    assert (plan.new, plan.changed, plan.unchanged, plan.stale) == (["c"], ["b"], 1, ["z"])


def test_a_field_added_outside_the_csv_counts_as_changed():
    docs = {"a": {"term": "a", "definition": "1"}}
    existing = {"a": {"term": "a", "definition": "1", "note": "added in the console"}}
    assert make_plan(docs, existing).changed == ["a"]


def test_first_import_writes_everything():
    store = FakeStore()
    code, _ = run(store, docs_n(10))
    assert code == 0 and store.writes == 10 and store.data == docs_n(10)


def test_second_import_of_the_same_file_writes_nothing():
    store = FakeStore()
    run(store, docs_n(50))
    before = store.writes
    code, lines = run(store, docs_n(50))
    assert code == 0 and store.writes == before and store.commits == 1
    assert any("unchanged 50" in line for line in lines)


def test_only_the_changed_rows_are_written():
    store = FakeStore()
    run(store, docs_n(100))
    docs = docs_n(100)
    docs["t5"]["definition"] = "edited"                                      # changed
    docs["t100"] = {"term": "t100", "definition": "brand new"}               # new
    store.writes = 0
    code, _ = run(store, docs)
    assert code == 0 and store.writes == 2  # not 101
    assert store.data["t5"]["definition"] == "edited" and "t100" in store.data


def test_plan_only_writes_nothing():
    store = FakeStore()
    code, lines = run(store, docs_n(20), plan_only=True)
    assert code == 0 and store.writes == 0 and store.commits == 0
    assert any("nothing was written" in line for line in lines)


def test_force_rewrites_everything():
    store = FakeStore()
    run(store, docs_n(30))
    store.writes = 0
    run(store, docs_n(30), force=True)
    assert store.writes == 30


def test_stale_documents_are_kept_unless_prune_is_set():
    store = FakeStore({"old": {"term": "old", "definition": "x"}})
    run(store, docs_n(3))
    assert "old" in store.data and store.deletes == 0
    run(store, docs_n(3), prune=True)
    assert "old" not in store.data and store.deletes == 1


def test_batches_never_exceed_the_limit():
    store = FakeStore()
    run(store, docs_n(BATCH * 2 + 1))
    assert store.writes == BATCH * 2 + 1 and store.commits == 3


def test_quota_exhaustion_stops_cleanly_and_the_next_run_finishes():
    docs = docs_n(BATCH * 3)
    store = FakeStore(fail_commit_number=3)  # the third batch hits the quota
    code, lines = run(store, docs)
    assert code == 1 and store.writes == BATCH * 2
    assert any("daily write quota" in line and "finishes the rest" in line for line in lines)
    store.fail_commit_number = None
    store.writes = 0
    code, _ = run(store, docs)
    assert code == 0 and store.writes == BATCH  # only the part that never got written
    assert store.data == docs


def test_other_errors_are_not_swallowed():
    class Boom(Exception):
        pass

    class Broken(FakeStore):
        def batch(self):
            raise Boom("network")

    try:
        run(Broken(), docs_n(3))
    except Boom:
        return
    raise AssertionError("an unexpected error must propagate")


def test_module_has_no_import_time_dependency_on_firebase():
    assert "firebase_admin" not in vars(import_terms)
