// The order ajax_helpers runs a response's commands in when the page is busy: process_commands,
// resume_commands and the poll behind them, in both clients. Run with `node --test js_tests/`.
//
// The block that does it needs only window.setTimeout / clearTimeout, ajax_helpers.ajax_busy and
// command_functions, so it is cut out of each file and run against a fake clock and stub commands.
// The `delay` command is checked against the whole of ajax_helpers.js, loaded with a stub DOM.

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const STATIC = path.join(__dirname, '..', 'ajax_helpers', 'static', 'ajax_helpers');
const CLIENTS = ['ajax_helpers.js', 'ajax_helpers_legacy.js'];
const BLOCK = /( *)\/\/ Paused responses, oldest first[\s\S]*?\n\1function process_commands\(commands\) \{\n[\s\S]*?\n\1\}\n/;

function fake_clock() {
    let now = 0;
    let next_id = 0;
    let timers = [];
    return {
        window: {
            setTimeout(fn, ms) {
                const timer = {id: ++next_id, at: now + (ms || 0), fn};
                timers.push(timer);
                return timer.id;
            },
            clearTimeout(id) {
                timers = timers.filter((timer) => timer.id !== id);
            },
        },
        // Runs every timer due by `to`, in time order; returns what they threw.
        advance(to) {
            const thrown = [];
            for (;;) {
                timers.sort((a, b) => a.at - b.at || a.id - b.id);
                const timer = timers[0];
                if (!timer || timer.at > to) {
                    break;
                }
                timers.shift();
                now = timer.at;
                try {
                    timer.fn();
                } catch (error) {
                    thrown.push(error);
                }
            }
            now = to;
            return thrown;
        },
        pending: () => timers.length,
        get now() {
            return now;
        },
    };
}

// The queue block of one client, with commands that log, hold the page, close a modal at once
// (hidden.bs.modal inside the command, resuming from there, as django_modals does), run nested
// commands as an `if` does, and throw.
function load(client) {
    const source = fs.readFileSync(path.join(STATIC, client), 'utf8');
    const block = source.match(BLOCK);
    assert.ok(block, `no command queue block in ${client}`);
    const clock = fake_clock();
    const log = [];
    const ajax_helpers = {ajax_busy: false};
    let queue;
    const command_functions = {
        log: (c) => log.push(c.v),
        hold: (c) => {
            log.push(c.v);
            ajax_helpers.ajax_busy = true;
        },
        close_at_once: (c) => {
            log.push(c.v);
            ajax_helpers.ajax_busy = true;
            ajax_helpers.ajax_busy = false;
            queue.resume_commands();
        },
        nest: (c) => {
            log.push(c.v);
            queue.process_commands([...c.commands]);
        },
        boom: (c) => {
            log.push(c.v);
            throw new Error(c.v);
        },
    };
    queue = new Function(
        'window',
        'ajax_helpers',
        'command_functions',
        `${block[0]}\nreturn {process_commands, resume_commands, waiting: () => waiting_commands.length};`,
    )(clock.window, ajax_helpers, command_functions);
    // The page goes idle the way django_modals lets it: the flag cleared, then a resume.
    const idle = () => {
        ajax_helpers.ajax_busy = false;
        queue.resume_commands();
    };
    return {queue, clock, log, ajax_helpers, idle};
}

const run = (...commands) => commands.map(([fn, v, extra]) => ({function: fn, v, ...extra}));

for (const client of CLIENTS) {
    test(`${client}: a fading close holds what follows it until the modal has gone`, () => {
        const {queue, log, idle} = load(client);
        queue.process_commands(run(['hold', 'close'], ['log', 'send_inputs']));
        queue.process_commands(run(['log', 'show_modal']));
        idle();
        assert.deepEqual(log, ['close', 'send_inputs', 'show_modal']);
    });

    test(`${client}: a close that finishes at once runs the rest of its response first`, () => {
        // Drained: both were waiting.
        let t = load(client);
        t.ajax_helpers.ajax_busy = true;
        t.queue.process_commands(run(['close_at_once', 'close'], ['log', 'send_inputs']));
        t.queue.process_commands(run(['hold', 'show_modal']));
        t.idle();
        assert.deepEqual(t.log, ['close', 'send_inputs', 'show_modal']);

        // Fresh: the closing response starts while an older one waits.
        t = load(client);
        t.ajax_helpers.ajax_busy = true;
        t.queue.process_commands(run(['hold', 'show_modal']));
        t.ajax_helpers.ajax_busy = false;
        t.queue.process_commands(run(['close_at_once', 'close'], ['log', 'send_inputs']));
        assert.deepEqual(t.log, ['close', 'send_inputs', 'show_modal']);
    });

    test(`${client}: waiting responses keep their order through a poll that finds the page busy`, () => {
        const {queue, clock, log, ajax_helpers, idle} = load(client);
        ajax_helpers.ajax_busy = true;
        queue.process_commands(run(['log', 'A']));
        clock.advance(50);
        queue.process_commands(run(['log', 'B']));
        clock.advance(110);
        assert.deepEqual(log, []);
        clock.advance(125);
        idle();
        assert.deepEqual(log, ['A', 'B']);
    });

    test(`${client}: what a response runs through process_commands comes before the rest of it`, () => {
        const nested = run(['nest', 'if', {commands: run(['hold', 'delay'], ['log', 'child'])}], ['log', 'parent']);

        // Resumed from the queue, with a newer response behind it.
        let t = load(client);
        t.ajax_helpers.ajax_busy = true;
        t.queue.process_commands(structuredClone(nested));
        t.queue.process_commands(run(['log', 'later']));
        t.idle();
        t.idle();
        assert.deepEqual(t.log, ['if', 'delay', 'child', 'parent', 'later']);

        // Fresh, with an older response waiting.
        t = load(client);
        t.ajax_helpers.ajax_busy = true;
        t.queue.process_commands(run(['log', 'older']));
        t.ajax_helpers.ajax_busy = false;
        t.queue.process_commands(structuredClone(nested));
        t.idle();
        assert.deepEqual(t.log, ['if', 'delay', 'child', 'parent', 'older']);
    });

    test(`${client}: a fresh response that pauses stays ahead of the ones already waiting`, () => {
        // The flag cleared without a resume (anything outside this library), the poll still due.
        const {queue, log, ajax_helpers, idle} = load(client);
        ajax_helpers.ajax_busy = true;
        queue.process_commands(run(['hold', 'show_modal']));
        ajax_helpers.ajax_busy = false;
        queue.process_commands(run(['hold', 'close'], ['log', 'send_inputs']));
        idle();
        idle();
        assert.deepEqual(log, ['close', 'send_inputs', 'show_modal']);
    });

    test(`${client}: a command that throws in the drain ends only its own response`, () => {
        const {queue, clock, log, ajax_helpers, idle} = load(client);
        ajax_helpers.ajax_busy = true;
        queue.process_commands(run(['boom', 'E1'], ['log', 'E2']));
        queue.process_commands(run(['log', 'F']));
        assert.doesNotThrow(idle);
        assert.deepEqual(log, ['E1', 'F']);
        assert.equal(queue.waiting(), 0);
        const thrown = clock.advance(clock.now);
        assert.deepEqual(thrown.map((error) => error.message), ['E1']);
    });

    test(`${client}: a resume asked for mid-response that then pauses leaves one copy and one poll`, () => {
        const {queue, clock, log, ajax_helpers} = load(client);
        queue.process_commands(run(['close_at_once', 'close'], ['hold', 'show_modal'], ['log', 'after']));
        assert.deepEqual(log, ['close', 'show_modal']);
        assert.equal(queue.waiting(), 1);
        assert.equal(clock.pending(), 1);
        ajax_helpers.ajax_busy = false;
        clock.advance(clock.now + 100);
        assert.deepEqual(log, ['close', 'show_modal', 'after']);
        assert.equal(queue.waiting(), 0);
        assert.equal(clock.pending(), 0);
    });

    test(`${client}: an idle page runs a response straight away`, () => {
        const {queue, clock, log} = load(client);
        queue.process_commands(run(['log', 'G']));
        assert.deepEqual(log, ['G']);
        assert.equal(clock.pending(), 0);
    });

    test(`${client}: a large backlog drains in linear time`, () => {
        const {queue, log, ajax_helpers, idle} = load(client);
        ajax_helpers.ajax_busy = true;
        for (let i = 0; i < 5000; i++) {
            queue.process_commands(run(['log', i]));
        }
        const started = process.hrtime.bigint();
        idle();
        const ms = Number(process.hrtime.bigint() - started) / 1e6;
        assert.equal(log.length, 5000);
        assert.ok(ms < 250, `5000 responses took ${ms}ms`);
    });
}

// Anything at all: enough DOM for ajax_helpers.js to load.
function anything() {
    const target = function () {};
    return new Proxy(target, {
        get: (_, key) => (key === Symbol.toPrimitive ? () => '' : anything()),
        apply: () => anything(),
        construct: () => anything(),
    });
}

test('ajax_helpers.js: the end of a delay runs what waited for it then, not at the next poll', () => {
    const clock = fake_clock();
    const window = {...clock.window, addEventListener() {}, location: {href: 'http://test/'}};
    const context = vm.createContext({
        window,
        document: anything(),
        navigator: anything(),
        history: anything(),
        location: window.location,
        XMLHttpRequest: anything(),
        FormData: anything(),
        setTimeout: window.setTimeout,
        clearTimeout: window.clearTimeout,
        console,
    });
    vm.runInContext(`${fs.readFileSync(path.join(STATIC, 'ajax_helpers.js'), 'utf8')}\nthis.ajax_helpers = ajax_helpers;`, context);
    const ajax_helpers = context.ajax_helpers;
    const log = [];
    ajax_helpers.command_functions.log = (c) => log.push(c.v);

    ajax_helpers.process_commands([{function: 'delay', time: 30}, {function: 'log', v: 'after delay'}]);
    assert.deepEqual(log, []);
    clock.advance(30);
    assert.deepEqual(log, ['after delay']);
});
