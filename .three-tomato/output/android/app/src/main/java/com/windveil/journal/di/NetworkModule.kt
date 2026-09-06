package com.windveil.journal.di

import android.content.Context
import com.windveil.journal.BuildConfig
import com.windveil.journal.data.local.CookieJarStore
import com.windveil.journal.data.local.TokenStore
import com.windveil.journal.data.remote.AuthApi
import com.windveil.journal.data.remote.AuthInterceptor
import com.windveil.journal.data.remote.TokenAuthenticator
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.android.qualifiers.ApplicationContext
import dagger.hilt.components.SingletonComponent
import okhttp3.OkHttpClient
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import java.util.concurrent.TimeUnit
import javax.inject.Qualifier
import javax.inject.Singleton

@Qualifier
@Retention(AnnotationRetention.BINARY)
annotation class RefreshRetrofit

@Module
@InstallIn(SingletonComponent::class)
object NetworkModule {

    @Provides
    @Singleton
    fun cookieJar(@ApplicationContext context: Context): CookieJarStore = CookieJarStore(context)

    @Provides
    @Singleton
    fun okHttpClient(
        cookieJar: CookieJarStore,
        authInterceptor: AuthInterceptor,
        tokenAuthenticator: TokenAuthenticator,
    ): OkHttpClient = OkHttpClient.Builder()
        .cookieJar(cookieJar)
        .addInterceptor(authInterceptor)
        .authenticator(tokenAuthenticator)
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .build()

    @Provides
    @Singleton
    fun retrofit(client: OkHttpClient): Retrofit = Retrofit.Builder()
        .baseUrl(BuildConfig.API_BASE_URL)
        .client(client)
        .addConverterFactory(GsonConverterFactory.create())
        .build()

    /**
     * 刷新专用通道：只带 CookieJar、不带 authenticator，
     * 避免 /auth/refresh 的 401（REFRESH_INVALID）再次进入刷新循环。
     */
    @Provides
    @Singleton
    @RefreshRetrofit
    fun refreshRetrofit(cookieJar: CookieJarStore): Retrofit = Retrofit.Builder()
        .baseUrl(BuildConfig.API_BASE_URL)
        .client(
            OkHttpClient.Builder()
                .cookieJar(cookieJar)
                .connectTimeout(15, TimeUnit.SECONDS)
                .readTimeout(30, TimeUnit.SECONDS)
                .build()
        )
        .addConverterFactory(GsonConverterFactory.create())
        .build()

    @Provides
    @Singleton
    @RefreshRetrofit
    fun refreshAuthApi(@RefreshRetrofit retrofit: Retrofit): AuthApi = retrofit.create(AuthApi::class.java)

    @Provides @Singleton fun authApi(retrofit: Retrofit): AuthApi = retrofit.create(AuthApi::class.java)
    @Provides @Singleton fun preferenceApi(retrofit: Retrofit): com.windveil.journal.data.remote.PreferenceApi = retrofit.create(com.windveil.journal.data.remote.PreferenceApi::class.java)
    @Provides @Singleton fun wishesApi(retrofit: Retrofit): com.windveil.journal.data.remote.WishesApi = retrofit.create(com.windveil.journal.data.remote.WishesApi::class.java)
    @Provides @Singleton fun memoriesApi(retrofit: Retrofit): com.windveil.journal.data.remote.MemoriesApi = retrofit.create(com.windveil.journal.data.remote.MemoriesApi::class.java)
    @Provides @Singleton fun liteEventsApi(retrofit: Retrofit): com.windveil.journal.data.remote.LiteEventsApi = retrofit.create(com.windveil.journal.data.remote.LiteEventsApi::class.java)
    @Provides @Singleton fun mediaApi(retrofit: Retrofit): com.windveil.journal.data.remote.MediaApi = retrofit.create(com.windveil.journal.data.remote.MediaApi::class.java)
    @Provides @Singleton fun systemApi(retrofit: Retrofit): com.windveil.journal.data.remote.SystemApi = retrofit.create(com.windveil.journal.data.remote.SystemApi::class.java)
    @Provides @Singleton fun holidaysApi(retrofit: Retrofit): com.windveil.journal.data.remote.HolidaysApi = retrofit.create(com.windveil.journal.data.remote.HolidaysApi::class.java)

    @Provides
    @Singleton
    fun tokenAuthenticator(
        tokenStore: TokenStore,
        @RefreshRetrofit refreshAuthApi: AuthApi,
    ): TokenAuthenticator = TokenAuthenticator(tokenStore, object : TokenAuthenticator.RefreshApiProvider {
        override fun refreshApi(): AuthApi = refreshAuthApi
    })
}
