package com.windveil.journal.data.repository

import com.windveil.journal.data.remote.AnonymousRequest
import com.windveil.journal.data.remote.AuthApi
import com.windveil.journal.data.remote.AuthResult
import com.windveil.journal.data.remote.ChannelsUpdateRequest
import com.windveil.journal.data.remote.LinkEmailRequest
import com.windveil.journal.data.remote.LoginRequest
import com.windveil.journal.data.local.TokenStore
import com.windveil.journal.data.remote.NotificationChannels
import com.windveil.journal.data.remote.OnboardingAnswer
import com.windveil.journal.data.remote.OnboardingAnswersRequest
import com.windveil.journal.data.remote.UserProfile
import com.windveil.journal.data.remote.bodyOrThrow
import com.windveil.journal.data.remote.okOrThrow
import javax.inject.Inject
import javax.inject.Singleton

/** S01：匿名建号、首次体验、邮箱绑定与登录（对应 auth.yaml）。 */
@Singleton
class AuthRepository @Inject constructor(
    private val authApi: AuthApi,
    private val tokenStore: TokenStore,
) {
    /** S01 Step 3 → Step 6：点「开始」即建号，无表单。 */
    suspend fun createAnonymousSpace(): UserProfile {
        val result = authApi.createAnonymousSpace(AnonymousRequest()).bodyOrThrow()
        tokenStore.save(result.accessToken)
        return result.user
    }

    suspend fun login(email: String, password: String): AuthResult {
        val result = authApi.login(LoginRequest(email, password)).bodyOrThrow()
        tokenStore.save(result.accessToken)
        return result
    }

    suspend fun linkEmail(email: String, password: String): UserProfile =
        authApi.linkEmail(LinkEmailRequest(email, password)).bodyOrThrow()

    suspend fun getMe(): UserProfile = authApi.getMe().bodyOrThrow()

    /** 跳过全部问题时提交空数组（S01 Step 9 → Step 11）。 */
    suspend fun submitOnboarding(answers: List<OnboardingAnswer>) {
        authApi.submitOnboardingAnswers(OnboardingAnswersRequest(answers)).okOrThrow()
    }

    suspend fun updateChannels(pushEnabled: Boolean? = null, emailEnabled: Boolean? = null): NotificationChannels =
        authApi.updateNotificationChannels(ChannelsUpdateRequest(pushEnabled, emailEnabled)).bodyOrThrow()

    suspend fun logout() {
        runCatching { authApi.logout().okOrThrow() }
        tokenStore.clear()
    }
}
