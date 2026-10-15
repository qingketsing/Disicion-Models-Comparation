# Jev 主实验 40 条错误的 AI 审阅

日期：2026-10-15。**全部案例说明由 AI 审阅生成，非人工评审。** 仅用于解释固定 test 上的错误模式；不能据这些案例修改冻结类别说明、真值或重新筛选测量。

来源：v4 retry3 第一轮 main `results/20261015T012952Z-main-full-seed42-rep1-jev-eaa8b9bc`，2974 条逻辑请求最终全部 ok，其中 415 条与原始真值不一致。以下按频次最高的 20 个混淆方向各取第一条，再以随机种子 42 从剩余错误抽取至 40 条，保持 sample_id 唯一。它是定性诊断样本，不代表各类错误的无偏比例；网络失败与恢复另报，不混作语义分类错误。

“歧义、上下文不足、标注疑点”等是 AI 解释假设，未由人工或数据集维护者核验。所有评分仍严格使用原始数据集真值；合法输出并不保证语义正确。目录60类中 cooking_query 在完整 test 没有真值支持，但模型可合法预测它，因此会计为错误与对应假阳性。

| # | sample_id | 原始文本 | 冻结真值 | Jev预测 | AI审阅（非人工） |
| --- | --- | --- | --- | --- | --- |
| 1 | massive-en-US-test-13175 | check celebrity where abouts | general_quirky | qa_factoid | 将名人行踪当作事实问答；数据集将这条归入闲聊，类别边界可能依赖数据集约定。 |
| 2 | massive-en-US-test-6725 | remind me about my schedule for the afternoon | calendar_set | calendar_query | 句首提醒动作指向设置提醒，预测偏向查询既有日程；存在查询内容与设置动作混合。 |
| 3 | massive-en-US-test-10038 | i need good ideas for cooking | cooking_recipe | cooking_query | 烹饪灵感/食谱请求被分到一般烹饪查询；cooking_query虽无test真值，仍是允许预测的目录标签。 |
| 4 | massive-en-US-test-3600 | remind me after ten minutes | calendar_set | alarm_set | 相对时间提醒在日历提醒与闹钟之间混淆；应按冻结真值计错，不能根据直觉改标。 |
| 5 | massive-en-US-test-1127 | play all songs on shuffle | play_music | music_settings | 播放动作和shuffle设置并存，模型选择播放设置；属于动作优先级边界。 |
| 6 | massive-en-US-test-1400 | i mostly pay attention | weather_query | general_quirky | 孤立文本缺乏天气线索，原真值为weather_query；可能存在上下文缺失或数据歧义，仅作AI疑点。 |
| 7 | massive-en-US-test-9233 | open pandora | play_radio | play_music | Pandora应用名可能指向广播/流媒体，模型选音乐；依赖实体及服务类型知识。 |
| 8 | massive-en-US-test-11257 | olly play next recording | play_podcasts | music_settings | 下一条录音的控制动作被归为播放设置，数据集预期播客；文本未显式给出播客类型。 |
| 9 | massive-en-US-test-13044 | i want tickets to the sold out concert on saturday night | general_quirky | recommendation_events | 售罄演出票务请求被分为活动推荐，真值为闲聊；目录的业务边界与日常语义不完全一致。 |
| 10 | massive-en-US-test-15185 | birthday wishes | social_post | general_quirky | 极短的生日祝福缺少发布平台/动词，模型选择闲聊，数据集预期社交发布。 |
| 11 | massive-en-US-test-3598 | how about you | general_quirky | general_greet | 简短反问可能是寒暄或一般闲聊，模型选择问候，反映近邻意图边界。 |
| 12 | massive-en-US-test-13074 | why isn't adam sandler funny | qa_factoid | general_quirky | 对演员是否好笑的评价问句被判闲聊，而真值为事实问答；主观措辞容易改变分类。 |
| 13 | massive-en-US-test-13297 | who is celebrity | qa_factoid | qa_definition | who is与模糊名词触发定义类别，真值为事实问答；问题对象不明确。 |
| 14 | massive-en-US-test-1423 | tell me about trump | news_query | qa_factoid | 人物介绍与人物新闻查询混淆；原句没有显式时效线索，仍遵循原真值。 |
| 15 | massive-en-US-test-15364 | can you let amazon know that this new phone case is junk | social_post | email_sendemail | 向Amazon表达产品投诉被当作发邮件，真值为社交发布；沟通渠道未明确。 |
| 16 | massive-en-US-test-15828 | here is a new email address to be added to the contacts | email_sendemail | email_addcontact | 句面是添加联系人，原真值却为发邮件；AI提出标注/上下文疑点，未核实且不改GT。 |
| 17 | massive-en-US-test-1744 | what do you think | music_likeness | general_quirky | 孤立的意见问句缺少音乐对象，模型选择闲聊，真值为音乐喜好；疑似依赖缺失上下文。 |
| 18 | massive-en-US-test-7113 | will there any events downtown this weekend | calendar_query | recommendation_events | 查询周末市中心活动被当作活动推荐，数据集预期日历查询；公共活动与个人日程边界。 |
| 19 | massive-en-US-test-12310 | give me the list of available train tickets from edinburgh to leeds | transport_query | transport_ticket | 列出可用火车票是交通信息查询，模型选择购票类别；检索与交易动作混淆。 |
| 20 | massive-en-US-test-13404 | what store is having sales tomorrow | general_quirky | recommendation_locations | 商店促销信息被判地点推荐，真值为闲聊；开放域购物信息与推荐边界。 |
| 21 | massive-en-US-test-9895 | keep playing secret garden | play_audiobook | play_game | Secret Garden的媒体实体可能不明确，模型预测游戏而真值为有声书；需要实体类型辨别。 |
| 22 | massive-en-US-test-7073 | search my calendar for my next event and notify me before it occurs | calendar_set | calendar_query | 前半句搜索日历，后半句要求事前通知；模型选查询而忽略设置提醒动作。 |
| 23 | massive-en-US-test-9138 | when does the super bowl officially start | qa_factoid | datetime_query | Super Bowl开场时间是事件事实，模型选日期时间查询；事件知识与通用时间工具边界。 |
| 24 | massive-en-US-test-4973 | olly play i can't feel my face | play_music | play_game | 歌词/歌名和play组合被错分游戏，真值为音乐；专名识别或短语歧义。 |
| 25 | massive-en-US-test-13222 | where does kate middleton buy her kids clothes | general_quirky | qa_factoid | 名人购物习惯被当事实问答，原真值为闲聊；数据集对名人闲聊的边界。 |
| 26 | massive-en-US-test-1401 | i occasionally pay attention | weather_query | general_quirky | 原句缺少天气对象，模型选闲聊，真值天气；与另一pay attention案例相似的上下文缺失疑点。 |
| 27 | massive-en-US-test-9760 | stop play | play_audiobook | music_settings | 停止播放未说明媒体类型，模型选音乐设置，真值有声书；省略媒体上下文导致类型混淆。 |
| 28 | massive-en-US-test-8345 | let me know when the meeting is gonna happen | calendar_set | calendar_query | 通知会议时间可能是询问也可能设提醒，模型选查询，真值设日历；通知意图优先级。 |
| 29 | massive-en-US-test-13547 | where was will ferrell seen last night | general_quirky | qa_factoid | 名人昨晚行踪被选事实问答，真值闲聊；与高频名人话题错误一致。 |
| 30 | massive-en-US-test-9986 | boiling | cooking_recipe | qa_definition | 单词boiling可指烹饪也可询问定义，模型选定义，真值食谱；极短输入信息不足。 |
| 31 | massive-en-US-test-13298 | what does celebrity do | qa_factoid | qa_definition | what does celebrity do被当词义解释，真值事实问答；对象名词泛化触发定义。 |
| 32 | massive-en-US-test-15966 | send a reply if it is very important | email_query | email_sendemail | 条件性回复动作被选择发邮件，真值邮件查询；条件筛选与发送动作混合。 |
| 33 | massive-en-US-test-2451 | seven hundred | datetime_convert | qa_maths | 裸数字缺少转换单位/时区，模型选数学，真值时间转换；上下文不足的潜在歧义。 |
| 34 | massive-en-US-test-5134 | find songs from my big band playlist | play_music | music_query | find songs偏向音乐检索，真值为播放音乐；检索与启动播放的动作边界。 |
| 35 | massive-en-US-test-13154 | do you know jessica snout's phone number | qa_factoid | email_querycontact | 电话号码问题被当联系人查询，真值事实问答；私人通讯录和外部人物知识边界。 |
| 36 | massive-en-US-test-11427 | start the gilmore guys | play_podcasts | play_music | Gilmore Guys播客实体被当音乐，缺少显式podcast提示时依赖实体知识。 |
| 37 | massive-en-US-test-4001 | what happened on the walking dead | news_query | qa_factoid | 电视剧剧情回顾被当事实问答，真值新闻查询；娱乐资讯与事实问答边界。 |
| 38 | massive-en-US-test-7876 | what's been happening for the last two months | news_query | general_quirky | 时间跨度的泛问没有新闻关键词，模型选闲聊，真值新闻；需推断语境。 |
| 39 | massive-en-US-test-9291 | put on | play_radio | iot_wemo_on | put on缺少宾语，模型选开关设备，真值广播；严重省略输入的多义性。 |
| 40 | massive-en-US-test-4955 | would you love to see | iot_hue_lightchange | general_quirky | 孤立短语没有灯光/颜色线索，模型选闲聊，原真值灯光换色；可能依赖未提供上下文，AI未核实。 |
