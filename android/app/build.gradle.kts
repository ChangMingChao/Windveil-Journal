plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("com.google.dagger.hilt.android")
    id("com.google.devtools.ksp")
}

// Room schema 导出：迁移 JSON 落到 app/schemas/，供 MigrationTestHelper 与人工比对（#14）
ksp {
    arg("room.schemaLocation", "$projectDir/schemas")
}

android {
    namespace = "com.windveil.journal"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.windveil.journal"
        minSdk = 26
        targetSdk = 34
        versionCode = 7
        versionName = "0.4.1"
    }

    buildTypes {
        release {
            isMinifyEnabled = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
        }
    }

    buildFeatures {
        compose = true
        buildConfig = true
    }
    composeOptions {
        kotlinCompilerExtensionVersion = "1.5.8"
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }
}

dependencies {
    // Core
    implementation("androidx.core:core-ktx:1.12.0")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.7.0")
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.7.0")
    implementation("androidx.activity:activity-compose:1.8.2")

    // Compose
    implementation(platform("androidx.compose:compose-bom:2024.02.01"))
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.ui:ui-tooling-preview")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.material:material-icons-extended")
    implementation("androidx.navigation:navigation-compose:2.7.7")

    // Hilt
    implementation("com.google.dagger:hilt-android:2.50")
    ksp("com.google.dagger:hilt-compiler:2.50")
    implementation("androidx.hilt:hilt-navigation-compose:1.1.0")

    // 网络：OkHttp（心语直连用户自配模型端点）+ Gson（JSON 序列化）
    // 旧服务端契约（Retrofit 接口/模型/测试）已整体移到 test 源集，不进发布包
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
    implementation("com.google.code.gson:gson:2.10.1")

    // 本地存储：DataStore（access token）
    implementation("androidx.datastore:datastore-preferences:1.0.0")

    // 图片：Coil
    implementation("io.coil-kt:coil-compose:2.5.0")

    // 单机模式：Room 本地库
    implementation("androidx.room:room-runtime:2.6.1")
    implementation("androidx.room:room-ktx:2.6.1")
    ksp("androidx.room:room-compiler:2.6.1")

    // 协程 Play services 不需要；日历走 ContentResolver

    // 单元测试（include_tests: true）；旧服务端契约也留在测试源集做契约回归
    testImplementation("junit:junit:4.13.2")
    testImplementation("com.squareup.okhttp3:mockwebserver:4.12.0")
    testImplementation("org.jetbrains.kotlinx:kotlinx-coroutines-test:1.7.3")
    testImplementation("com.google.truth:truth:1.4.2")
    testImplementation("com.squareup.retrofit2:retrofit:2.9.0")
    testImplementation("com.squareup.retrofit2:converter-gson:2.9.0")

    debugImplementation("androidx.compose.ui:ui-tooling")
}
