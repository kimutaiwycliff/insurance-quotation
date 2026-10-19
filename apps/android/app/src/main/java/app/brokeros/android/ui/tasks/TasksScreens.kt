package app.brokeros.android.ui.tasks

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material3.Checkbox
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FloatingActionButton
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.ListItem
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.PrimaryTabRow
import androidx.compose.material3.Tab
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewModelScope
import app.brokeros.android.core.Dates
import app.brokeros.android.core.Labels
import app.brokeros.android.data.AppException
import app.brokeros.android.data.BrokerApi
import app.brokeros.android.data.EntityRef
import app.brokeros.android.data.Task
import app.brokeros.android.data.TaskInput
import app.brokeros.android.data.createTask
import app.brokeros.android.data.newIdempotencyKey
import app.brokeros.android.data.tasks
import app.brokeros.android.data.updateTask
import app.brokeros.android.ui.components.Choices
import app.brokeros.android.ui.components.DateField
import app.brokeros.android.ui.components.Empty
import app.brokeros.android.ui.components.Field
import app.brokeros.android.ui.components.FormError
import app.brokeros.android.ui.components.Load
import app.brokeros.android.ui.components.Loaded
import app.brokeros.android.ui.components.LocalToast
import app.brokeros.android.ui.components.SubmitButton
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

private val TABS = listOf("overdue" to "Overdue", "today" to "Today", "upcoming" to "Upcoming", "done" to "Done")

class TasksViewModel(private val api: BrokerApi, private val entity: EntityRef? = null) : ViewModel() {
    private val _state = MutableStateFlow<Load<List<Task>>>(Load.Loading)
    val state = _state.asStateFlow()
    var tab = if (entity == null) "today" else "all"
        private set

    init { load() }

    fun show(tab: String) {
        this.tab = tab
        load()
    }

    fun load() = viewModelScope.launch {
        _state.value = Load.Loading
        _state.value = try {
            val list = when (tab) {
                "done" -> api.tasks(due = "all", status = "done", entityType = entity?.entityType, entityId = entity?.entityId)
                else -> api.tasks(due = tab, status = "open", entityType = entity?.entityType, entityId = entity?.entityId)
            }
            Load.Ready(list)
        } catch (e: AppException) {
            Load.Failed(e.message ?: "Try again.")
        }
    }

    suspend fun toggle(task: Task) {
        api.updateTask(task, TaskInput(done = task.status != "done"))
        load()
    }
}

@Composable
fun TaskRow(task: Task, onToggle: () -> Unit, onOpen: () -> Unit) {
    val done = task.status == "done"
    val overdue = !done && task.dueAt != null && Dates.parseInstant(task.dueAt)?.isBefore(java.time.Instant.now()) == true
    ListItem(
        leadingContent = {
            Checkbox(
                checked = done,
                onCheckedChange = { onToggle() },
                modifier = Modifier.semantics { contentDescription = (if (done) "Mark not done: " else "Mark done: ") + task.title },
            )
        },
        headlineContent = { Text(task.title) },
        supportingContent = {
            val due = task.dueAt?.let { "Due ${Dates.relative(it)}" }
            val parts = listOfNotNull(due, task.priority.takeIf { it == "high" }?.let { "High priority" })
            if (parts.isNotEmpty()) {
                Text(parts.joinToString(" · "), color = if (overdue) MaterialTheme.colorScheme.error else Color.Unspecified)
            }
        },
        modifier = Modifier.padding(0.dp),
        trailingContent = { TextButton(onClick = onOpen) { Text("Edit") } },
    )
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun TasksScreen(viewModel: TasksViewModel, api: BrokerApi) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    var tab by rememberSaveable { mutableStateOf(viewModel.tab) }
    var editing by remember { mutableStateOf<Task?>(null) }
    var adding by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    val toast = LocalToast.current

    Box(Modifier.fillMaxSize()) {
        Column(Modifier.fillMaxSize()) {
            PrimaryTabRow(selectedTabIndex = TABS.indexOfFirst { it.first == tab }.coerceAtLeast(0)) {
                TABS.forEach { (key, label) ->
                    Tab(selected = tab == key, onClick = { tab = key; viewModel.show(key) }, text = { Text(label) })
                }
            }
            PullToRefreshBox(isRefreshing = state is Load.Loading, onRefresh = { viewModel.load() }, modifier = Modifier.fillMaxSize()) {
                Loaded(state, onRetry = { viewModel.load() }) { list ->
                    if (list.isEmpty()) {
                        Empty(if (tab == "done") "Nothing finished yet." else "Nothing here. Well done.")
                    } else {
                        LazyColumn(Modifier.fillMaxSize()) {
                            items(list, key = { it.id }) { task ->
                                TaskRow(
                                    task,
                                    onToggle = {
                                        scope.launch {
                                            try {
                                                viewModel.toggle(task)
                                                toast(if (task.status == "done") "Reopened: ${task.title}" else "Done: ${task.title}")
                                            } catch (e: AppException) {
                                                toast(e.message ?: "Try again.")
                                            }
                                        }
                                    },
                                    onOpen = { editing = task },
                                )
                                HorizontalDivider()
                            }
                        }
                    }
                }
            }
        }
        FloatingActionButton(onClick = { adding = true }, modifier = Modifier.align(Alignment.BottomEnd).padding(16.dp)) {
            Icon(Icons.Default.Add, contentDescription = "Add task")
        }
    }
    if (adding || editing != null) {
        TaskSheet(api = api, task = editing, entity = null, onDismiss = { adding = false; editing = null }) {
            adding = false; editing = null; viewModel.load()
        }
    }
}

/** Add or edit a task in a bottom sheet. Tasks added from a client are linked to it. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun TaskSheet(api: BrokerApi, task: Task?, entity: EntityRef?, onDismiss: () -> Unit, onSaved: () -> Unit) {
    var title by rememberSaveable { mutableStateOf(task?.title ?: "") }
    var due by remember { mutableStateOf(task?.dueAt?.let { Dates.parseInstant(it)?.atZone(Dates.zone())?.toLocalDate() }) }
    var priority by rememberSaveable { mutableStateOf(task?.priority ?: "normal") }
    var notes by rememberSaveable { mutableStateOf(task?.notes ?: "") }
    var error by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }
    val key = remember { newIdempotencyKey() }
    val scope = rememberCoroutineScope()
    val toast = LocalToast.current

    ModalBottomSheet(onDismissRequest = onDismiss) {
        Column(
            Modifier.padding(horizontal = 16.dp).padding(bottom = 24.dp).navigationBarsPadding(),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Text(if (task == null) "Add task" else "Edit task", style = MaterialTheme.typography.titleLarge)
            Field("What needs doing", title, { title = it })
            DateField("Due", due, { due = it })
            Choices("Priority", listOf("low", "normal", "high"), priority, { priority = it ?: "normal" })
            Field("Notes", notes, { notes = it }, singleLine = false, minLines = 2)
            FormError(error)
            SubmitButton(if (task == null) "Add task" else "Save task", busy, title.isNotBlank()) {
                busy = true
                scope.launch {
                    try {
                        val input = TaskInput(
                            title = title.trim(),
                            dueAt = due?.let(Dates::morningOf),
                            priority = priority,
                            notes = notes.trim().ifBlank { null },
                            entityType = if (task == null) entity?.entityType else null,
                            entityId = if (task == null) entity?.entityId else null,
                        )
                        if (task == null) api.createTask(input, key) else api.updateTask(task, input)
                        toast(if (task == null) "Task added" else "Task saved")
                        onSaved()
                    } catch (e: AppException) {
                        error = e.message
                    } finally {
                        busy = false
                    }
                }
            }
            if (task != null) {
                Text("Status: ${Labels.of(task.status)}", style = MaterialTheme.typography.bodySmall)
            }
        }
    }
}
