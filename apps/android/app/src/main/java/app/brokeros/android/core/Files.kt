package app.brokeros.android.core

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.net.Uri
import android.provider.OpenableColumns
import androidx.core.content.FileProvider
import java.io.ByteArrayOutputStream
import java.io.File

/** A file ready to upload. */
class Picked(val name: String, val bytes: ByteArray, val mime: String)

object Files {
    /** Longest side of a photo after shrinking: sharp enough for an ID or logbook, light on mobile data. */
    private const val MAX_SIDE = 1800
    private const val SHRINK_ABOVE_BYTES = 700_000

    /** A fresh file in the app's cache for the camera to write into, as a content URI. */
    fun newCapture(context: Context): Uri {
        val dir = File(context.cacheDir, "captures").apply { mkdirs() }
        val file = File.createTempFile("photo-", ".jpg", dir)
        return FileProvider.getUriForFile(context, "${context.packageName}.files", file)
    }

    /** Save a PDF to the cache and open it in the phone's PDF viewer. False if no viewer is installed. */
    fun openPdf(context: Context, bytes: ByteArray, name: String): Boolean {
        val dir = File(context.cacheDir, "pdfs").apply { mkdirs() }
        val file = File(dir, name.replace(Regex("[^A-Za-z0-9._-]"), "_").let { if (it.endsWith(".pdf")) it else "$it.pdf" })
        file.writeBytes(bytes)
        val uri = FileProvider.getUriForFile(context, "${context.packageName}.files", file)
        val intent = android.content.Intent(android.content.Intent.ACTION_VIEW)
            .setDataAndType(uri, "application/pdf")
            .addFlags(android.content.Intent.FLAG_GRANT_READ_URI_PERMISSION or android.content.Intent.FLAG_ACTIVITY_NEW_TASK)
        return runCatching { context.startActivity(intent) }.isSuccess
    }

    fun read(context: Context, uri: Uri): Picked {
        val resolver = context.contentResolver
        val mime = resolver.getType(uri) ?: "application/octet-stream"
        val name = resolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)?.use { c ->
            if (c.moveToFirst()) c.getString(0) else null
        } ?: "upload-${System.currentTimeMillis()}"
        val bytes = resolver.openInputStream(uri)?.use { it.readBytes() } ?: ByteArray(0)
        if (mime.startsWith("image/") && mime != "image/gif" && bytes.size > SHRINK_ABOVE_BYTES) {
            shrink(bytes)?.let { return Picked(name.substringBeforeLast('.') + ".jpg", it, "image/jpeg") }
        }
        return Picked(name, bytes, mime)
    }

    /** Downscale a large photo to [MAX_SIDE] and re-encode as JPEG 85; null if it can't be decoded. */
    fun shrink(bytes: ByteArray): ByteArray? {
        val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        BitmapFactory.decodeByteArray(bytes, 0, bytes.size, bounds)
        if (bounds.outWidth <= 0) return null
        var sample = 1
        while (maxOf(bounds.outWidth, bounds.outHeight) / (sample * 2) >= MAX_SIDE) sample *= 2
        val decoded = BitmapFactory.decodeByteArray(bytes, 0, bytes.size, BitmapFactory.Options().apply { inSampleSize = sample })
            ?: return null
        val scale = MAX_SIDE.toFloat() / maxOf(decoded.width, decoded.height)
        val bitmap = if (scale < 1f) {
            Bitmap.createScaledBitmap(decoded, (decoded.width * scale).toInt(), (decoded.height * scale).toInt(), true)
        } else {
            decoded
        }
        return ByteArrayOutputStream().use { out ->
            bitmap.compress(Bitmap.CompressFormat.JPEG, 85, out)
            out.toByteArray()
        }.takeIf { it.size < bytes.size }
    }
}
