package com.windveil.journal.di

import android.content.Context
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.android.qualifiers.ApplicationContext
import dagger.hilt.components.SingletonComponent
import javax.inject.Singleton

// standalone-mode：本 App 不装配任何服务端契约网络栈（Retrofit/OkHttp 已随契约代码移出主源集）。
// 心语模型直连走 HeartVoiceClient（用户自配 HTTPS 端点），节假日走 assets 打包数据。
@Module
@InstallIn(SingletonComponent::class)
object DatabaseModule {
    @Provides
    @Singleton
    fun database(@ApplicationContext context: Context): com.windveil.journal.data.local.db.WindveilDatabase =
        com.windveil.journal.data.local.db.WindveilDatabase.get(context)
}
