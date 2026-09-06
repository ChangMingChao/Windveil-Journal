package com.windveil.journal

import com.google.gson.Gson
import com.windveil.journal.data.remote.SeedWishResult
import com.windveil.journal.data.remote.WishDetail
import com.windveil.journal.data.remote.WishListResponse
import com.windveil.journal.data.remote.LiteEvent
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * 契约反序列化测试 —— JSON 样例严格取自 logos/resources/api 目录下各 yaml 契约 的 schema 字段。
 */
class ModelsParsingTest {

    private val gson = Gson()

    @Test
    fun `解析 WishDetail（含时机、理解与待确认建议）`() {
        val json = """
        {
          "id": "6f1e2c3a-0000-4000-8000-000000000001",
          "title": "去看海",
          "original_text_excerpt": "想一个人去看海",
          "seeded_at": "2026-09-01T08:00:00Z",
          "let_go_at": null,
          "state": "brewing",
          "timing": {"type": "season", "label": "正在等待合适的风：入冬", "trigger_kind": "time", "next_trigger_at": "2026-11-01T09:00:00Z"},
          "soft_deferred": false,
          "degraded_reason": null,
          "version": 3,
          "original_text": "想一个人去看海",
          "audio_media_id": null,
          "photo_media_ids": [],
          "understanding": {"kind": "future_wish", "feeling": "放松", "conditions": {"season": "winter"}, "smallest_step": "查一下喜欢的那片海"},
          "pending_question": false,
          "timing_proposal": {
            "id": "6f1e2c3a-0000-4000-8000-0000000000aa",
            "wish_id": "6f1e2c3a-0000-4000-8000-000000000001",
            "status": "pending",
            "timing_type": "season",
            "timing_value": "winter",
            "proposed_trigger_at": "2026-11-01T09:00:00Z",
            "reason": "因为你说过喜欢冷天的安静",
            "confidence": 72,
            "evidence": [{"kind": "preference", "id": "p1"}],
            "validation": {"valid": true, "reason_code": null},
            "created_at": "2026-09-05T09:00:00Z",
            "expires_at": "2026-09-12T09:00:00Z",
            "decided_at": null
          },
          "amended_from": null,
          "current_step": null,
          "timeline": [],
          "messages": []
        }
        """.trimIndent()

        val wish = gson.fromJson(json, WishDetail::class.java)

        assertEquals("去看海", wish.title)
        assertEquals("brewing", wish.state)
        assertEquals(3, wish.version)
        assertEquals("正在等待合适的风：入冬", wish.timing.label)
        assertEquals("winter", wish.timingProposal?.timingValue)
        assertEquals(true, wish.timingProposal?.validation?.valid)
        assertEquals("放松", wish.understanding?.feeling)
        assertNull(wish.letGoAt)
    }

    @Test
    fun `解析愿望列表（游标分页，无计数字段）`() {
        val json = """
        {
          "items": [
            {"id": "w1", "title": "重新开始画画", "seeded_at": "2026-09-02T08:00:00Z",
             "state": "seeded", "timing": {"type": "none", "label": "你说你会自己想起它", "trigger_kind": "none", "next_trigger_at": null}, "version": 1}
          ],
          "next_cursor": null
        }
        """.trimIndent()

        val page = gson.fromJson(json, WishListResponse::class.java)
        assertEquals(1, page.items.size)
        assertEquals("none", page.items[0].timing.triggerKind)
        assertNull(page.nextCursor)
    }

    @Test
    fun `解析种下结果（降级时 question 为 null，actions 含轻事件选项）`() {
        val json = """
        {
          "wish": {"id": "w2", "title": "周末取快递", "seeded_at": "2026-09-05T08:00:00Z",
                   "state": "seeded", "timing": {"type": "none", "label": "你说你会自己想起它", "trigger_kind": "none", "next_trigger_at": null}, "version": 1},
          "question": null,
          "actions": ["keep_as_future", "save_as_lite", "delete"],
          "degraded": true
        }
        """.trimIndent()

        val result = gson.fromJson(json, SeedWishResult::class.java)
        assertTrue(result.degraded)
        assertNull(result.question)
        assertTrue(result.actions.orEmpty().contains("save_as_lite"))
    }

    @Test
    fun `解析轻事件（open 与 done 状态配对）`() {
        val json = """
        {"id": "e1", "text": "今晚吃火锅", "status": "open",
         "created_at": "2026-09-05T10:00:00Z", "closed_at": null}
        """.trimIndent()

        val event = gson.fromJson(json, LiteEvent::class.java)
        assertEquals("open", event.status)
        assertNull(event.closedAt)
        assertEquals("今晚吃火锅", event.text)
    }
}
