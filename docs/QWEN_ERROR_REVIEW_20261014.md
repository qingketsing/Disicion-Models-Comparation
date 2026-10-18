# Qwen v4 代表错误的 AI 审阅记录

来源：完整 test 第一轮 2974 条，固定 guidance 后端，目录和数据冻结。抽样规则：按错误混淆对频次取前 20 对的各一条，然后从剩余错误中以 seed=42 抽取 20 条，共 40 个不同样本。此表由 AI 审阅，非人工审阅；它不是错误类别总体频率的无偏估计。原始真值全部保留，没有据测试错误修改提示词、类别说明或标签。

| 样本 ID | 原始文本 | 真值 | 预测 | 审阅说明 |
|---|---|---|---|---|
| massive-en-US-test-12987 | can you track my emotions based on the way i speak | general_quirky | general_greet | 请求推断情绪，不是问候；把非常规助手对话归为问候。 |
| massive-en-US-test-1047 | i need a good cry can you play me sad rock songs | play_music | music_query | 明确包含 play；混淆播放动作与查询音乐。 |
| massive-en-US-test-15763 | please check for new emails | email_query | email_querycontact | 查询新邮件；误选联系人相关邮件查询。 |
| massive-en-US-test-6850 | list out my schedule today | calendar_query | datetime_query | 查询日程列表；混淆日历事件与时间查询。 |
| massive-en-US-test-13400 | send a funny message to all of my friends | social_post | general_greet | 请求向朋友发送消息；没有识别发布或发送意图。 |
| massive-en-US-test-13124 | how big is the cosmos | qa_factoid | weather_query | 宇宙大小是事实问题；与天气类别不符。 |
| massive-en-US-test-10023 | what do i need to make lamb pathia | cooking_recipe | cooking_query | 请求制作菜肴所需材料；配方与烹饪信息类别存在边界重叠。 |
| massive-en-US-test-1351 | will it be nice outside this week | weather_query | general_greet | 询问本周室外天气；问候类别与内容不符。 |
| massive-en-US-test-10772 | remove my dentist's appointment from today's schedule | calendar_remove | alarm_remove | 删除牙医预约；把日历删除与闹钟删除混淆。 |
| massive-en-US-test-15756 | please email my team | email_sendemail | email_addcontact | 要求给团队发邮件；混淆发送与添加联系人。 |
| massive-en-US-test-13078 | tell me billy crytals address | qa_factoid | general_greet | 询问人物地址；不属于问候。 |
| massive-en-US-test-1276 | i want a coffee | iot_coffee | cooking_query | 咖啡请求按原标注为设备制作；短文本也缺少明确设备上下文。 |
| massive-en-US-test-13177 | remind me to move so there is no weight gain | calendar_set | general_greet | 提醒活动按数据标注为日历设置；模型没有识别提醒动作。 |
| massive-en-US-test-15765 | answer to pawel's email | email_sendemail | email_querycontact | 要求回复邮件；误选联系人查询。 |
| massive-en-US-test-13457 | tell me when i should leave for a scheduled event so that i am on time | calendar_set | datetime_query | 请求提醒何时出发；与只查询时间的类别混淆。 |
| massive-en-US-test-11628 | where is the pharmacy in leavenworth | recommendation_locations | transport_query | 寻找药房位置；混淆地点推荐与交通查询。 |
| massive-en-US-test-1264 | is my alarm set for tomorrow morning | alarm_query | alarm_set | 询问闹钟是否已经设置；混淆状态查询与设置动作。 |
| massive-en-US-test-12951 | what is the highest building in the world | qa_factoid | datetime_query | 查询最高建筑事实；与时间查询不符。 |
| massive-en-US-test-12999 | how old is mariah carey | qa_factoid | qa_definition | 查询人物年龄；混淆事实问答与概念定义。 |
| massive-en-US-test-13625 | what is the largest desk | qa_definition | general_greet | 数据标为定义；文本“最大的桌子”本身不够明确，保留原真值。 |
| massive-en-US-test-16271 | refresh my inbox and inform me about new emails | email_query | email_querycontact | 刷新收件箱并告知新邮件；不应限定为联系人邮件查询。 |
| massive-en-US-test-12367 | what's the best way to sheffield | transport_query | general_greet | 询问前往城市的路线；没有识别交通查询。 |
| massive-en-US-test-6305 | what do you want to do today | general_quirky | general_greet | 开放式助手对话按原标注为 quirky；不等同问候。 |
| massive-en-US-test-7014 | give me the schedule for today's events | calendar_query | datetime_query | 查询当天事件日程；模型只识别时间关键词。 |
| massive-en-US-test-9542 | let me listen the latest news program on radio | play_radio | news_query | 收听广播新闻；混淆播放渠道与新闻查询内容。 |
| massive-en-US-test-11767 | olly what events are happening in pondichery this weekend | recommendation_events | calendar_query | 询问城市周末活动；混淆公共活动推荐与个人日历。 |
| massive-en-US-test-2451 | seven hundred | datetime_convert | general_greet | 仅“seven hundred”缺少转换对象；输入上下文不足，不能据此修改原标注。 |
| massive-en-US-test-11164 | away off from list | lists_remove | iot_wemo_off | 列表删除指令措辞残缺；错误关注 off 并选择设备关闭。 |
| massive-en-US-test-13591 | what is the capitol of west virginia | qa_factoid | datetime_query | 州府是事实问题；与时间查询不符。 |
| massive-en-US-test-9528 | turn on some n. p. r. and play them out of my speakers | play_radio | iot_hue_lighton | 要求播放 NPR 广播；错误关联 turn on 与灯光开启。 |
| massive-en-US-test-16914 | do i have emails from this sender | email_query | email_querycontact | 按发件人检索邮箱；原类别为一般邮件查询，邻近类别边界容易混淆。 |
| massive-en-US-test-9284 | play f. m. | play_radio | play_music | 播放 FM 广播；误将广播渠道归为音乐播放。 |
| massive-en-US-test-1151 | start vacuum cleaner | iot_cleaning | iot_coffee | 启动吸尘器；混淆两种智能设备任务。 |
| massive-en-US-test-1510 | quiet mode on until i am home from work | audio_volume_mute | general_greet | 静音模式请求；未识别音量控制。 |
| massive-en-US-test-11180 | my party planning | calendar_query | general_greet | “my party planning”缺少动作；依赖数据集上下文的日历查询，问候也不符。 |
| massive-en-US-test-13464 | why are we here | general_quirky | general_greet | 开放式哲学对话；误归为问候。 |
| massive-en-US-test-14040 | how tall is hulk hogan | qa_factoid | music_query | 人物身高是事实查询；与音乐查询不符。 |
| massive-en-US-test-5258 | save this song to playlist | music_likeness | music_query | 将歌曲保存到列表按原标注为喜好；未识别对歌曲的操作。 |
| massive-en-US-test-14150 | what are converse shoes | qa_definition | music_likeness | 询问鞋类定义；与音乐喜好不符。 |
| massive-en-US-test-8914 | what time is my appointment on april fourth | calendar_query | datetime_query | 查询预约时间；混淆事件日程与一般时间。 |
