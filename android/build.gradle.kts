// Top-level build file. Configuration is declared per-module in app/build.gradle.kts.
// AGP 9 compiles Kotlin itself (built-in Kotlin): no kotlin-android plugin.
plugins {
    alias(libs.plugins.android.application) apply false
    alias(libs.plugins.kotlin.compose) apply false
}
