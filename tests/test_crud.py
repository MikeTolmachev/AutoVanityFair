import pytest


def test_create_and_get_post(post_crud):
    post_id = post_crud.create("Test post content", strategy="thought_leadership")
    assert post_id > 0

    post = post_crud.get(post_id)
    assert post is not None
    assert post["content"] == "Test post content"
    assert post["strategy"] == "thought_leadership"
    assert post["status"] == "draft"


def test_post_status_transitions(post_crud):
    post_id = post_crud.create("Test post")

    post_crud.update_status(post_id, "approved")
    assert post_crud.get(post_id)["status"] == "approved"

    post_crud.update_status(post_id, "published")
    post = post_crud.get(post_id)
    assert post["status"] == "published"
    assert post["published_at"] is not None


def test_post_rejection(post_crud):
    post_id = post_crud.create("Bad post")
    post_crud.update_status(post_id, "rejected", reason="Low quality")

    post = post_crud.get(post_id)
    assert post["status"] == "rejected"
    assert post["rejection_reason"] == "Low quality"


def test_list_by_status(post_crud):
    post_crud.create("Draft 1")
    post_crud.create("Draft 2")
    pid3 = post_crud.create("Approved")
    post_crud.update_status(pid3, "approved")

    drafts = post_crud.list_by_status("draft")
    assert len(drafts) == 2

    approved = post_crud.list_by_status("approved")
    assert len(approved) == 1


def test_update_content(post_crud):
    post_id = post_crud.create("Original content")
    post_crud.update_content(post_id, "Updated content")
    assert post_crud.get(post_id)["content"] == "Updated content"


def test_count_by_status(post_crud):
    post_crud.create("A")
    post_crud.create("B")
    pid = post_crud.create("C")
    post_crud.update_status(pid, "approved")

    counts = post_crud.count_by_status()
    assert counts["draft"] == 2
    assert counts["approved"] == 1


def test_create_and_get_comment(comment_crud):
    cid = comment_crud.create(
        target_post_url="https://linkedin.com/post/123",
        comment_content="Great insights!",
        target_post_author="John",
        strategy="grounded",
        confidence=0.85,
    )
    assert cid > 0

    comment = comment_crud.get(cid)
    assert comment["comment_content"] == "Great insights!"
    assert comment["strategy"] == "grounded"
    assert comment["confidence"] == 0.85


def test_comment_status_transitions(comment_crud):
    cid = comment_crud.create(
        target_post_url="https://linkedin.com/post/456",
        comment_content="Nice post",
    )
    comment_crud.update_status(cid, "approved")
    assert comment_crud.get(cid)["status"] == "approved"

    comment_crud.update_status(cid, "published")
    comment = comment_crud.get(cid)
    assert comment["status"] == "published"
    assert comment["published_at"] is not None


def test_interaction_log(log_crud):
    lid = log_crud.log("generate_post", target_url="https://example.com", details="test")
    assert lid > 0

    recent = log_crud.get_recent(limit=5)
    assert len(recent) == 1
    assert recent[0]["action_type"] == "generate_post"


def test_interaction_count_by_action(log_crud):
    log_crud.log("generate_post")
    log_crud.log("generate_post")
    log_crud.log("publish_comment")

    counts = log_crud.count_by_action(days=7)
    assert counts["generate_post"] == 2
    assert counts["publish_comment"] == 1


def test_content_library_crud(content_crud):
    doc_id = content_crud.add(
        title="Test Doc",
        content="Some content",
        source="test",
        tags=["ai", "ml"],
    )
    assert doc_id > 0

    doc = content_crud.get(doc_id)
    assert doc["title"] == "Test Doc"

    assert content_crud.count() == 1

    all_docs = content_crud.list_all()
    assert len(all_docs) == 1

    content_crud.delete(doc_id)
    assert content_crud.count() == 0


def test_get_nonexistent(post_crud, comment_crud):
    assert post_crud.get(9999) is None
    assert comment_crud.get(9999) is None
