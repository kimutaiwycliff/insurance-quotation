# kotlinx.serialization: keep generated serializers for our API models.
-keepattributes *Annotation*, InnerClasses
-keep,includedescriptorclasses class app.brokeros.android.**$$serializer { *; }
-keepclassmembers class app.brokeros.android.** {
    *** Companion;
}
-keepclasseswithmembers class app.brokeros.android.** {
    kotlinx.serialization.KSerializer serializer(...);
}
# Ktor and OkHttp reference optional platform classes.
-dontwarn org.slf4j.**
-dontwarn org.conscrypt.**
-dontwarn org.bouncycastle.**
-dontwarn org.openjsse.**
