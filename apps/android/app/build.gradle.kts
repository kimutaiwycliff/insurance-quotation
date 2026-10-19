plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.compose)
    alias(libs.plugins.kotlin.serialization)
}

// Release settings come from Gradle properties (-P...) or CI environment, never from the repo (ADR-0026).
fun setting(name: String, default: String): String =
    (findProperty(name) as String?) ?: System.getenv(name.uppercase()) ?: default

// The application ID can never change once the app is on Google Play: finalise it with the product name.
val appId = setting("appId", "app.brokeros.android")

android {
    namespace = "app.brokeros.android"
    compileSdk = 37

    defaultConfig {
        applicationId = appId
        minSdk = 26
        targetSdk = 37
        versionCode = setting("versionCode", "1").toInt()
        versionName = setting("versionName", "0.1.0")
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }

    signingConfigs {
        val keystore = System.getenv("ANDROID_UPLOAD_KEYSTORE")
        if (keystore != null) {
            create("upload") {
                storeFile = file(keystore)
                storePassword = System.getenv("ANDROID_UPLOAD_KEYSTORE_PASSWORD")
                keyAlias = System.getenv("ANDROID_UPLOAD_KEY_ALIAS")
                keyPassword = System.getenv("ANDROID_UPLOAD_KEY_PASSWORD")
            }
        }
    }

    buildTypes {
        debug {
            // The Android emulator reaches the computer's local stack (make up) at 10.0.2.2.
            buildConfigField("String", "SITE_URL", "\"${setting("siteUrl", "http://10.0.2.2:3000")}\"")
            buildConfigField("String", "API_URL", "\"${setting("apiUrl", "http://10.0.2.2:8000")}\"")
            // The auth service trusts the web app's origin; locally that is localhost, not 10.0.2.2.
            buildConfigField("String", "AUTH_ORIGIN", "\"${setting("authOrigin", "http://localhost:3000")}\"")
            buildConfigField("String", "LOCALHOST_ALIAS", "\"${setting("localhostAlias", "10.0.2.2")}\"")
            applicationIdSuffix = ".debug"
        }
        release {
            buildConfigField("String", "SITE_URL", "\"${setting("siteUrl", "https://app.example.invalid")}\"")
            buildConfigField("String", "API_URL", "\"${setting("apiUrl", "https://api.example.invalid")}\"")
            buildConfigField("String", "AUTH_ORIGIN", "\"${setting("siteUrl", "https://app.example.invalid")}\"")
            buildConfigField("String", "LOCALHOST_ALIAS", "\"\"")
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
            signingConfigs.findByName("upload")?.let { signingConfig = it }
        }
    }

    // direct: downloaded from our own site, updates itself (checked by SHA-256). play: Google Play, in-app updates.
    flavorDimensions += "store"
    productFlavors {
        create("direct") {
            dimension = "store"
            buildConfigField("String", "DISTRIBUTION", "\"direct\"")
        }
        create("play") {
            dimension = "store"
            buildConfigField("String", "DISTRIBUTION", "\"play\"")
        }
    }

    buildFeatures {
        compose = true
        buildConfig = true
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    lint {
        warningsAsErrors = false
        abortOnError = true
        checkReleaseBuilds = true
    }

    testOptions {
        unitTests.isReturnDefaultValues = true
    }
}

dependencies {
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.activity.compose)
    implementation(libs.androidx.lifecycle.viewmodel.compose)
    implementation(libs.androidx.lifecycle.runtime.compose)
    implementation(libs.androidx.navigation.compose)
    implementation(libs.androidx.datastore.preferences)
    implementation(libs.androidx.work.runtime)
    implementation(platform(libs.compose.bom))
    implementation(libs.compose.ui)
    implementation(libs.compose.ui.tooling.preview)
    implementation(libs.compose.material3)
    implementation(libs.compose.material.icons.core)
    "playImplementation"(libs.play.app.update)
    "playImplementation"(libs.androidx.fragment.ktx)
    implementation(libs.ktor.client.core)
    implementation(libs.ktor.client.okhttp)
    implementation(libs.ktor.client.content.negotiation)
    implementation(libs.ktor.serialization.json)
    implementation(libs.kotlinx.serialization.json)
    implementation(libs.kotlinx.coroutines.android)
    debugImplementation(libs.compose.ui.tooling)

    testImplementation(libs.junit)
    testImplementation(libs.kotlinx.coroutines.test)
    testImplementation(libs.ktor.client.mock)
}
