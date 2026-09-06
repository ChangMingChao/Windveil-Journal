# 实现任务

## [delta] 规格变更
- [ ] `api/wishes.yaml`：TimingInput.type 增 `holiday`、新增 `holidays: string[]`；新增 `GET /holidays`（timing tag）
- [ ] 需求文档 5.3 心语表述归属修订（android-native-app → heart-voice-holiday-timing）
- [ ] `test/core-S03-test-cases.md`：新增 holiday 计算 UT 条目

## [code] 代码实现
- [ ] 后端：`holidays.py` 增 next_holiday_occurrence；`timing.py` 增 holiday 类型；`services.py`/`api.py` 透传 + `GET /holidays`
- [ ] 后端 UT：holiday 计算（命中/多选取最近/数据缺失报 TIMING_INVALID）
- [ ] Android：底栏四 Tab + Garden 顶部「愿望|随手记」切换
- [ ] Android：心语页（聊天 UI + 客户端直连 LLM + 有用信息自动记轻事件）
- [ ] Android：我的页大模型配置（Base URL / API Key / 模型名）
- [ ] Android：详情页时机区重构（节假日多选 + 年月日 + 让它提个时候）
- [ ] Android：详情页移除「整理它」（保留 它已经发生了 / 彻底删除）
- [ ] Android：「我的」页二级化——内容分类收入四个二级页（心语与模型 / 它记得我什么 / 提醒 / 账号），主页面改为菜单入口（用户 2026-09-06 追加）
- [ ] 构建部署模拟器 E2E 验证
