import java.util.Properties

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
}

// Signing material is never committed. Locally it comes from keystore.properties
// beside this file; in CI the workflow writes the same file from repository
// secrets. When neither is present the release APK is left unsigned, which is
// fine for a local build but not for something people install.
val keystoreProps = Properties().apply {
    val file = rootProject.file("keystore.properties")
    if (file.exists()) file.inputStream().use { load(it) }
}

fun signingValue(key: String, env: String): String? =
    (keystoreProps.getProperty(key) ?: System.getenv(env))?.takeIf { it.isNotBlank() }

// Named with a `ks` prefix on purpose: inside the signingConfig block below,
// `storeFile` and friends resolve to the signing config's own properties, so a
// same-named outer val would be shadowed and read back as null.
val ksFile = signingValue("storeFile", "FH_KEYSTORE_PATH")
val ksStorePassword = signingValue("storePassword", "FH_KEYSTORE_PASSWORD")
val ksKeyAlias = signingValue("keyAlias", "FH_KEY_ALIAS")
val ksKeyPassword = signingValue("keyPassword", "FH_KEY_PASSWORD")
val canSign = ksFile != null && ksStorePassword != null && ksKeyAlias != null && ksKeyPassword != null

// Version comes from the tag in CI (-PappVersionName=v1.0.0) and falls back to a
// literal for local builds. versionCode must only ever go up, or Android refuses
// the update and users have to uninstall first.
val appVersionName: String = (findProperty("appVersionName") as String?)?.removePrefix("v") ?: "1.6.1"
val appVersionCode: Int = (findProperty("appVersionCode") as String?)?.toIntOrNull() ?: 9

android {
    namespace = "com.freehands.console"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.freehands.console"
        minSdk = 26
        targetSdk = 35
        versionCode = appVersionCode
        versionName = appVersionName

        // Baked in so the app needs no setup screen for an address. Override
        // for a self-hosted deployment:
        //   ./gradlew assembleRelease -PfreehandsBaseUrl=https://your-host
        val baseUrl = (findProperty("freehandsBaseUrl") as String?)
            ?: "https://work-1-jopjdcxrigxgbupp.prod-runtime.all-hands.dev"
        buildConfigField("String", "BASE_URL", "\"$baseUrl\"")
        // The wake door. The main host is dead whenever the supervisor is, so
        // starting it has to go to a host that is still listening.
        val wakeUrl = (findProperty("freehandsWakeUrl") as String?)
            ?: "https://work-2-jopjdcxrigxgbupp.prod-runtime.all-hands.dev"
        buildConfigField("String", "WAKE_URL", "\"$wakeUrl\"")
    }

    signingConfigs {
        if (canSign) {
            create("release") {
                storeFile = file(ksFile!!)
                storePassword = ksStorePassword
                keyAlias = ksKeyAlias
                keyPassword = ksKeyPassword
                // Both schemes: v1 for old devices, v2/v3 for current ones.
                enableV1Signing = true
                enableV2Signing = true
                enableV3Signing = true
            }
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

    kotlinOptions {
        jvmTarget = "17"
    }

    buildTypes {
        release {
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro",
            )
            if (canSign) {
                signingConfig = signingConfigs.getByName("release")
            }
        }
    }

    // Names the artifact after the version so a downloaded file is identifiable
    // without opening it.
    applicationVariants.all {
        outputs.all {
            val out = this as com.android.build.gradle.internal.api.BaseVariantOutputImpl
            out.outputFileName = "freehands-$appVersionName.apk"
        }
    }
}

dependencies {
    implementation(platform("androidx.compose:compose-bom:2024.09.03"))
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.material:material-icons-extended")
    implementation("androidx.activity:activity-compose:1.9.2")
    // WindowCompat / WindowInsetsControllerCompat: hides the system bars for
    // full screen. activity-compose pulls core in transitively, but pinning it
    // keeps the version explicit instead of whatever a dependency resolves to.
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.8.6")
    implementation("androidx.lifecycle:lifecycle-runtime-compose:2.8.6")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.8.1")
    implementation("io.coil-kt:coil-compose:2.7.0")
    // Animated GIF/WebP support. Without this Coil draws only the first frame,
    // so a GIF in the log would look like a still picture.
    implementation("io.coil-kt:coil-gif:2.7.0")
    debugImplementation("androidx.compose.ui:ui-tooling")
    testImplementation("junit:junit:4.13.2")
    // The android.jar stub throws on every org.json call, so parsing tests
    // would pass vacuously. This is the real implementation used at runtime.
    testImplementation("org.json:json:20240303")
}
