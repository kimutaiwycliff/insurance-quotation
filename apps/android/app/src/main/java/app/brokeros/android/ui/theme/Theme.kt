package app.brokeros.android.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight

// The web app's tokens: paper, ink, acacia (actions), maize (progress and the active marker).
val Acacia = Color(0xFF0E6B5C)
val Maize = Color(0xFFF2B705)
val Ink = Color(0xFF17302B)
val Paper = Color(0xFFF6F7F4)

private val Light = lightColorScheme(
    primary = Acacia,
    onPrimary = Color.White,
    primaryContainer = Color(0xFFD2EBE5),
    onPrimaryContainer = Ink,
    secondary = Maize,
    onSecondary = Ink,
    secondaryContainer = Color(0xFFFFF0C2),
    onSecondaryContainer = Ink,
    background = Paper,
    onBackground = Ink,
    surface = Color.White,
    onSurface = Ink,
    surfaceVariant = Color(0xFFEDF1EE),
    onSurfaceVariant = Color(0xFF4F625D),
    outline = Color(0xFFC3CEC8),
    error = Color(0xFFB42318),
)

private val Dark = darkColorScheme(
    primary = Color(0xFF3FB39D),
    onPrimary = Color(0xFF08201B),
    primaryContainer = Color(0xFF21403A),
    onPrimaryContainer = Color(0xFFE8EFEC),
    secondary = Maize,
    onSecondary = Ink,
    secondaryContainer = Color(0xFF4A3B05),
    onSecondaryContainer = Color(0xFFFFF0C2),
    background = Color(0xFF0F1F1C),
    onBackground = Color(0xFFE8EFEC),
    surface = Color(0xFF152A26),
    onSurface = Color(0xFFE8EFEC),
    surfaceVariant = Color(0xFF1D3631),
    onSurfaceVariant = Color(0xFFA3B8B1),
    outline = Color(0xFF35544D),
    error = Color(0xFFF97066),
)

private val Base = Typography()
private val BrokerTypography = Typography(
    displaySmall = Base.displaySmall.copy(fontWeight = FontWeight.SemiBold),
    headlineMedium = Base.headlineMedium.copy(fontWeight = FontWeight.SemiBold),
    headlineSmall = Base.headlineSmall.copy(fontWeight = FontWeight.SemiBold),
    titleLarge = Base.titleLarge.copy(fontWeight = FontWeight.SemiBold),
    titleMedium = Base.titleMedium.copy(fontWeight = FontWeight.SemiBold),
)

@Composable
fun BrokerTheme(dark: Boolean = isSystemInDarkTheme(), content: @Composable () -> Unit) {
    MaterialTheme(colorScheme = if (dark) Dark else Light, typography = BrokerTypography, content = content)
}
