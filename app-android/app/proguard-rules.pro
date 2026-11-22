# Reflection keep rules. Minification is on for release, so anything the
# framework constructs by name has to survive renaming or the app dies at
# runtime in a way that only reproduces in a release build.

# viewModel() builds the class by reflection. ConsoleViewModel is an
# AndroidViewModel, so the constructor it looks for takes an Application; a
# no-arg-only rule would keep the class but lose the constructor and crash on
# first use.
-keep class com.freehands.console.data.ConsoleViewModel {
    public <init>(android.app.Application);
}
-keepclassmembers class com.freehands.console.data.** {
    <init>(...);
}

# Compose runtime looks up composables and their synthetic members by name.
-keep class androidx.compose.runtime.** { *; }
-dontwarn androidx.compose.**

# Coil loads decoders and fetchers through service discovery.
-keep class coil.** { *; }
-dontwarn coil.**

# Keep annotations the lifecycle and Compose tooling read at runtime.
-keepattributes *Annotation*, InnerClasses, Signature, SourceFile, LineNumberTable
