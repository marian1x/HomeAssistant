import com.android.build.api.variant.BuildConfigField
import java.io.FileInputStream
import java.util.Properties

plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.compose)
}

// In-app updates come from GitHub Releases of this public repository (owner decision
// 2026-11-25, no Firebase). Override with -PupdateRepo=owner/repo, e.g. a releases-only
// public repo once the source repo becomes private again.
val updateRepo = (project.findProperty("updateRepo") as String?) ?: "marian1x/HomeAssistant"

// Release signing secrets stay out of git (keystore.properties, written by CI).
val keystorePropertiesFile = rootProject.file("keystore.properties")
val keystoreProperties = Properties().apply {
    if (keystorePropertiesFile.exists()) FileInputStream(keystorePropertiesFile).use { load(it) }
}
val hasReleaseSigning = keystorePropertiesFile.exists()

// CI passes -PversionCode=<run number>; every published APK gets a higher code.
val ciVersionCode = (project.findProperty("versionCode") as String?)?.toIntOrNull() ?: 1

android {
    namespace = "ro.salavat.casa"
    compileSdk = 37

    defaultConfig {
        applicationId = "ro.salavat.casa"
        minSdk = 26
        targetSdk = 36
        versionCode = ciVersionCode
        versionName = "1.0.$ciVersionCode"
    }

    signingConfigs {
        if (hasReleaseSigning) {
            create("release") {
                storeFile = rootProject.file(keystoreProperties["storeFile"] as String)
                storePassword = keystoreProperties["storePassword"] as String
                keyAlias = keystoreProperties["keyAlias"] as String
                keyPassword = keystoreProperties["keyPassword"] as String
            }
        }
    }

    buildTypes {
        debug {
            applicationIdSuffix = ".debug"
            versionNameSuffix = "-debug"
        }
        // Emulator build against the local mock server (synthetic data, no HA).
        // Cleartext is allowed ONLY to 10.0.2.2 (src/mock/res/xml).
        create("mock") {
            initWith(getByName("debug"))
            applicationIdSuffix = ".mock"
            versionNameSuffix = "-mock"
            matchingFallbacks += listOf("debug")
        }
        release {
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
            if (hasReleaseSigning) signingConfig = signingConfigs.getByName("release")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    buildFeatures {
        compose = true
        buildConfig = true
    }
    packaging {
        resources { excludes += "/META-INF/{AL2.0,LGPL2.1}" }
    }
}

androidComponents {
    onVariants { variant ->
        val base = if (variant.buildType == "mock") "http://10.0.2.2:8787/casa" else "https://salavat.home.ro/casa"
        variant.buildConfigFields?.put("BASE_URL", BuildConfigField("String", "\"$base\"", "Casa backend (server/app.py)"))
        variant.buildConfigFields?.put("UPDATE_REPO", BuildConfigField("String", "\"$updateRepo\"", "GitHub repo with APK releases"))
        // Only signed release builds update themselves; debug/mock builds never replace the app.
        variant.buildConfigFields?.put("UPDATES", BuildConfigField("boolean", (variant.buildType == "release").toString(), "in-app updater enabled"))
    }
}

dependencies {
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.lifecycle.runtime.ktx)
    implementation(libs.androidx.lifecycle.viewmodel.compose)
    implementation(libs.androidx.lifecycle.runtime.compose)
    implementation(libs.androidx.activity.compose)
    implementation(libs.androidx.fragment)
    implementation(libs.androidx.splashscreen)
    implementation(libs.androidx.biometric)

    implementation(platform(libs.androidx.compose.bom))
    implementation(libs.androidx.ui)
    implementation(libs.androidx.ui.graphics)
    implementation(libs.androidx.ui.tooling.preview)
    implementation(libs.androidx.material3)
    implementation(libs.androidx.material.icons.extended)

    implementation(libs.okhttp)
    implementation(libs.okhttp.sse)
    implementation(libs.kotlinx.coroutines.android)

    implementation(libs.androidx.work)

    debugImplementation(libs.androidx.ui.tooling)
    testImplementation(libs.junit)
    testImplementation(libs.json)
}
