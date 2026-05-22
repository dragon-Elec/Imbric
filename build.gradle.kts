plugins {
    kotlin("jvm") version "2.3.20"
    id("org.jetbrains.kotlin.plugin.serialization") version "2.3.20"
    id("org.jetbrains.compose") version "1.7.3"
    id("org.jetbrains.kotlin.plugin.compose") version "2.3.20"
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
    // Kotlin Stdlib
    implementation(kotlin("stdlib"))
    
    // Compose
    implementation(compose.desktop.currentOs)
    implementation(compose.runtime)
    implementation(compose.foundation)
    implementation(compose.material3)
    implementation(compose.components.resources)

    // Coroutines
    
    // Coroutines
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-core:1.10.0")
    
    // DateTime
    implementation("org.jetbrains.kotlinx:kotlinx-datetime:0.6.0")
    
    // JSON Serialization
    implementation("org.jetbrains.kotlinx:kotlinx-serialization-json:1.7.3")
    
    // UUID (Kotlin 2.1+ native - bundled in stdlib, no extra dependency needed)
    // implementation(kotlin("kotlin-uuid")) // Uncomment if using Kotlin < 2.1
    
    // Logging
    implementation("io.github.microutils:kotlin-logging-jvm:3.0.5")
    implementation("org.java-gi:gtk:0.15.0") {
        exclude(group = "org.java-gi", module = "glib")
        exclude(group = "org.java-gi", module = "gdkpixbuf")
    }

    
    // Java-GI base annotations
    compileOnly("org.jspecify:jspecify:1.0.0")

    // Testing
    testImplementation(kotlin("test"))
    testImplementation("org.jetbrains.kotlinx:kotlinx-coroutines-test:1.10.0")
}

kotlin {
    jvmToolchain {
        languageVersion.set(JavaLanguageVersion.of(25))
    }
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
    }
}
