package app.brokeros.android

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.ui.Modifier
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.launch
import app.brokeros.android.ui.BrokerRoot
import app.brokeros.android.ui.theme.BrokerTheme
import app.brokeros.android.update.Updater
import app.brokeros.android.update.createUpdater

class MainActivity : ComponentActivity() {
    private lateinit var updates: Updater

    /** A screen to open, from a phone notification ("open" extra). */
    private val openRoute = kotlinx.coroutines.flow.MutableStateFlow<String?>(null)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        updates = createUpdater(this)
        openRoute.value = intent?.getStringExtra(app.brokeros.android.work.Background.OPEN)
        val container = (application as BrokerApp).container
        setContent {
            BrokerTheme {
                Surface(modifier = Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) {
                    BrokerRoot(container, updates, BuildConfig.VERSION_CODE, BuildConfig.VERSION_NAME, openRoute)
                }
            }
        }
    }

    override fun onNewIntent(intent: android.content.Intent) {
        super.onNewIntent(intent)
        intent.getStringExtra(app.brokeros.android.work.Background.OPEN)?.let { openRoute.value = it }
    }

    override fun onResume() {
        super.onResume()
        // Back from "allow installs from this app": carry on with the update.
        lifecycleScope.launch { updates.resume() }
        (application as BrokerApp).container.flush()
    }

    override fun onDestroy() {
        updates.close()
        super.onDestroy()
    }
}
