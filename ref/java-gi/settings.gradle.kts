plugins {
    id("org.gradle.toolchains.foojay-resolver-convention") version "1.0.0"
}

rootProject.name = "java-gi"

includeBuild("build-logic")
includeBuild("ext/javapoet")
includeBuild("generator")

include("glib")

// All child projects are located in the modules/ directory
for (p in rootProject.children) {
    p.projectDir = File(settingsDir, "modules/${p.name}")
}

include("ext")
