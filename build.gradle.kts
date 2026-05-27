plugins {
    kotlin("jvm") version "2.3.21"
    id("org.jetbrains.kotlin.plugin.serialization") version "2.3.21"
    id("org.jetbrains.compose") version "1.11.0"
    id("org.jetbrains.kotlin.plugin.compose") version "2.3.21"
    id("org.jetbrains.compose.hot-reload") version "1.1.0"
}

group = "com.imbric"
version = "0.1.0-SNAPSHOT"

sourceSets {
    main {
        java.srcDirs("build/native-gen/bindings")
    }
}

repositories {
    mavenCentral()
    google()
}

dependencies {
    // Force a single version of kotlinx-datetime to prevent Hot Reload classpath collisions
    configurations.all {
        resolutionStrategy.force("org.jetbrains.kotlinx:kotlinx-datetime:0.7.1")
    }

    implementation(compose.desktop.currentOs)
    implementation(compose.material3)
    implementation(compose.materialIconsExtended)
    implementation("com.materialkolor:material-kolor:2.0.0")
    
    // Use api to ensure visibility in Hot Reload isolated classpath
    api("org.jetbrains.kotlinx:kotlinx-datetime:0.7.1")
    
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-core:1.10.1")
    implementation("org.jetbrains.kotlinx:kotlinx-serialization-json:1.8.0")
    implementation("io.github.microutils:kotlin-logging-jvm:3.0.5")
    
    // GIO Bindings foundation
    compileOnly("org.jspecify:jspecify:1.0.0")
    implementation("org.java-gi:gtk:0.15.0") {
        exclude(group = "org.java-gi", module = "glib")
        exclude(group = "org.java-gi", module = "gdkpixbuf")
    }

    // Testing
    testImplementation(kotlin("test"))
    testImplementation("org.jetbrains.kotlinx:kotlinx-coroutines-test:1.10.0")
}

kotlin {
    jvmToolchain {
        languageVersion.set(JavaLanguageVersion.of(25))
    }
}

composeCompiler {
    // OptimizeNonSkippingGroups is enabled by default in Compose 1.11.0
}

tasks.test {
    useJUnitPlatform()
    jvmArgs("--enable-native-access=ALL-UNNAMED")
    testLogging {
        events("passed", "skipped", "failed")
        showStandardStreams = false
    }
}

compose.desktop {
    application {
        mainClass = "com.imbric.app.bootstrap.MainKt"
        jvmArgs += "--enable-native-access=ALL-UNNAMED"
        jvmArgs += "-XX:+AllowEnhancedClassRedefinition"
    }
}
