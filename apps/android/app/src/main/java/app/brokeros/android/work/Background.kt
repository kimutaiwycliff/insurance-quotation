package app.brokeros.android.work

import android.Manifest
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.NetworkType
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import app.brokeros.android.BrokerApp
import app.brokeros.android.MainActivity
import app.brokeros.android.R
import app.brokeros.android.data.notifications
import java.util.concurrent.TimeUnit

/**
 * Background work without Google services: every 30 minutes (when online) the app sends offline changes and
 * checks for new notifications, showing them on the phone. Push (FCM) can replace the polling later.
 */
object Background {
    private const val WORK = "background-sync"
    const val CHANNEL = "updates"
    const val OPEN = "open"

    fun start(context: Context) {
        val request = PeriodicWorkRequestBuilder<SyncWorker>(30, TimeUnit.MINUTES)
            .setConstraints(Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build())
            .build()
        WorkManager.getInstance(context).enqueueUniquePeriodicWork(WORK, ExistingPeriodicWorkPolicy.KEEP, request)
    }

    fun stop(context: Context) {
        WorkManager.getInstance(context).cancelUniqueWork(WORK)
        context.getSharedPreferences("background", Context.MODE_PRIVATE).edit().clear().apply()
        NotificationManagerCompat.from(context).cancelAll()
    }

    fun channel(context: Context) {
        val manager = context.getSystemService(NotificationManager::class.java)
        manager.createNotificationChannel(
            NotificationChannel(CHANNEL, "Updates from your agency", NotificationManager.IMPORTANCE_DEFAULT).apply {
                description = "Quotes accepted, invoices opened and other news"
            },
        )
    }

    fun canNotify(context: Context): Boolean =
        Build.VERSION.SDK_INT < 33 ||
            ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED
}

class SyncWorker(context: Context, params: WorkerParameters) : CoroutineWorker(context, params) {
    override suspend fun doWork(): Result {
        val container = (applicationContext as BrokerApp).container
        // Not signed in: nothing to do (and nothing to show).
        runCatching { container.session.apiToken() }.getOrElse { return Result.success() }
        runCatching { container.outbox.flush { container.api.replay(it) } }
        val prefs = applicationContext.getSharedPreferences("background", Context.MODE_PRIVATE)
        val seen = prefs.getStringSet("seen", emptySet()).orEmpty()
        val fresh = runCatching { container.api.notifications().items }.getOrNull()
            ?.filter { it.readAt == null && it.id !in seen }
            .orEmpty()
        if (fresh.isNotEmpty() && Background.canNotify(applicationContext)) {
            Background.channel(applicationContext)
            val open = PendingIntent.getActivity(
                applicationContext,
                0,
                Intent(applicationContext, MainActivity::class.java).putExtra(Background.OPEN, "notifications")
                    .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP),
                PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
            )
            fresh.take(5).forEach { n ->
                val notification = NotificationCompat.Builder(applicationContext, Background.CHANNEL)
                    .setSmallIcon(R.drawable.ic_launcher_foreground)
                    .setContentTitle(n.title)
                    .setContentText(n.body)
                    .setStyle(NotificationCompat.BigTextStyle().bigText(n.body))
                    .setContentIntent(open)
                    .setAutoCancel(true)
                    .build()
                @Suppress("MissingPermission") // checked by canNotify
                NotificationManagerCompat.from(applicationContext).notify(n.id.hashCode(), notification)
            }
        }
        prefs.edit().putStringSet("seen", (seen + fresh.map { it.id }).toList().takeLast(200).toSet()).apply()
        return Result.success()
    }
}
