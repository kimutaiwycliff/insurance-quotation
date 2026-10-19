package app.brokeros.android

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.ui.Modifier
import app.brokeros.android.ui.BrokerRoot
import app.brokeros.android.ui.theme.BrokerTheme
import app.brokeros.android.update.PlayUpdates

class MainActivity : ComponentActivity() {
    private lateinit var updates: PlayUpdates

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        updates = PlayUpdates(this)
        val container = (application as BrokerApp).container
        setContent {
            BrokerTheme {
                Surface(modifier = Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) {
                    BrokerRoot(container, updates, BuildConfig.VERSION_CODE, BuildConfig.VERSION_NAME)
                }
            }
        }
    }

    override fun onDestroy() {
        updates.close()
        super.onDestroy()
    }
}
