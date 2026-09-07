package com.windveil.journal.data.remote

import com.google.gson.Gson
import retrofit2.Response

/** 统一把非 2xx 响应转成 [ApiException]（解析契约的 ErrorResponse）。 */
suspend fun <T> Response<T>.bodyOrThrow(): T {
    if (isSuccessful) {
        return body() ?: throw ApiException(code(), ErrorResponse(code = "EMPTY_BODY", message = "响应为空"))
    }
    val httpCode = code()
    val error = parseError(errorBody()?.string(), httpCode)
    throw ApiException(httpCode, error)
}

/** 204 类空响应的校验。 */
suspend fun <T> Response<T>.okOrThrow() {
    if (!isSuccessful) {
        val httpCode = code()
        throw ApiException(httpCode, parseError(errorBody()?.string(), httpCode))
    }
}

private fun parseError(raw: String?, httpCode: Int): ErrorResponse =
    runCatching {
        Gson().fromJson(raw, ErrorResponse::class.java)
    }.getOrNull() ?: ErrorResponse(code = "HTTP_$httpCode", message = "请求失败（$httpCode）")
