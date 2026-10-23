// Tasks & reminders. A reminder is a task with a due time; when it comes due
// Parzival announces it aloud and posts a notification (backend/tasks.py).
import { h, icon, iconButton, dueLabel } from '../dom.js';
import { post } from '../api.js';
import { sortTasks, toggleTask } from '../ui/context.js';
import { toast } from '../ui/feedback.js';

const PRESETS = [
  ['', 'No reminder'],
  ['5', 'Remind in 5 min'],
  ['15', 'Remind in 15 min'],
  ['30', 'Remind in 30 min'],
  ['60', 'Remind in 1 hour'],
  ['120', 'Remind in 2 hours'],
  ['custom', 'Custom…'],
];

export function createTasksView() {
  const text = h('input.input', { type: 'text', placeholder: 'What needs doing?', 'aria-label': 'Task', maxlength: '280', required: true });
  const when = h('select.select', { 'aria-label': 'Reminder' }, PRESETS.map(([v, label]) => h('option', { value: v }, label)));
  const minutes = h('input.input', { type: 'number', min: '1', max: '10080', value: '45', 'aria-label': 'Minutes until reminder' });
  const submit = h('button.btn.btn--primary', { type: 'submit' }, icon('plus'), 'Add');
  const form = h('form.task-form', {}, text, when, submit,
    h('label.task-form__custom', {}, 'Remind me in', minutes, 'minutes'));

  when.addEventListener('change', () => form.classList.toggle('is-custom', when.value === 'custom'));
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const value = text.value.trim();
    if (!value) return;
    const mins = when.value === 'custom' ? Number(minutes.value) : Number(when.value);
    if (when.value === 'custom' && !(mins > 0)) return toast('Enter how many minutes until the reminder.', 'warn');
    submit.disabled = true;
    try {
      await post('tasks', { text: value, due: mins ? Date.now() / 1000 + mins * 60 : null });
      text.value = '';
      toast(mins ? `Reminder set for ${mins >= 60 && mins % 60 === 0 ? `${mins / 60} h` : `${mins} min`} from now.` : 'Task added.', 'ok');
    } catch (err) {
      toast(err.message, 'error');
    } finally {
      submit.disabled = false;
      text.focus();
    }
  });

  const pendingList = h('div.task-list', { role: 'list' });
  const doneList = h('div.task-list', { role: 'list' });
  const doneCount = h('span');
  const completed = h('details.completed', {},
    h('summary', {}, doneCount, icon('chevron')),
    h('div', { style: { display: 'flex', justifyContent: 'flex-end', marginTop: '6px' } },
      h('button.btn.btn--sm.btn--ghost', { type: 'button', onclick: () => post('tasks/clear-completed').catch((e) => toast(e.message, 'error')) }, 'Clear completed')),
    doneList);

  const row = (task) => {
    const due = task.due && !task.done ? dueLabel(task.due) : null;
    const el = h('div.task.glass-lite', { role: 'listitem', dataset: { done: String(task.done) } },
      h('button.check', {
        type: 'button', role: 'checkbox', 'aria-checked': String(task.done),
        'aria-label': `Mark “${task.text}” ${task.done ? 'not done' : 'done'}`, onclick: () => toggleTask(task),
      }, icon('check')),
      h('span.task__text', {}, task.text),
      due ? h('span.due', { dataset: { overdue: String(due.overdue) }, title: new Date(task.due * 1000).toLocaleString() }, due.text) : h('span'),
      iconButton('trash', 'Delete task', async () => {
        el.classList.add('is-leaving');
        try { await post('tasks/delete', { id: task.id }); }
        catch (err) { el.classList.remove('is-leaving'); toast(err.message, 'error'); }
      }));
    return el;
  };

  const render = (store) => {
    const tasks = store.tasks || [];
    const pending = sortTasks(tasks.filter((t) => !t.done));
    const done = tasks.filter((t) => t.done).reverse();
    pendingList.replaceChildren(...(pending.length ? pending.map(row) : [
      h('div.empty-state', {}, h('span.empty-state__icon', {}, icon('tasks')),
        h('p.empty-state__title', {}, store.tasks ? 'You’re all caught up' : 'Loading tasks…'),
        h('p.empty-state__text', {}, 'Add one above, or say “remind me to call Sam in 30 minutes”.')),
    ]));
    doneList.replaceChildren(...done.map(row));
    doneCount.textContent = `Completed · ${done.length}`;
    completed.hidden = !done.length;
  };

  let timer = 0;
  return {
    el: h('div', {},
      form,
      h('h3.section-title', {}, 'Pending'),
      pendingList,
      completed,
      h('p.hint-line', {}, 'Voice: ', h('q', {}, 'remind me to stretch in 20 minutes'), ' · ', h('q', {}, 'add buy milk to my tasks'), ' · ', h('q', {}, 'what are my tasks'))),
    focus: () => text.focus(),
    onShow: (store) => {
      render(store);
      clearInterval(timer);
      timer = setInterval(() => render(store), 15_000);   // keep "in 4m" fresh
    },
    onHide: () => clearInterval(timer),
    update: (store, keys) => { if (keys.includes('tasks')) render(store); },
  };
}
