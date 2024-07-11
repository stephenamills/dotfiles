_patch_help() { 
    ps --help all  | \
    sed \
        -e  '/^ -y/ d' \
        -e 's/-M, Z/-M   /' \
        -e 's/-w, w/-w   /' \
        -e 's/-V, V, --version/-V, --version/' \
    
    cat <<-'EOF'
Miss Options:
    --forest         ascii art process tree
    --sort           specify sort order as: [+|-]key[,[+|-]key[,...]]
    --cumulative     include some dead child process data
    -y               do not show flags, show rss (only with -l)
EOF
}

_patch_table() { 
    _patch_table_edit_options \
        '--Group;*,[`_module_os_group`]' \
        '--format;*,[`_choice_column`]' \
        '--group;*,[`_module_os_group`]' \
        '--pid;*,[`_module_os_pid`]' \
        '--ppid;*,[`_module_os_pid`]' \
        '--quick-pid;*,[`_module_os_pid`]' \
        '--sid;*,[`_module_os_sid`]' \
        '--sort;*,[`_choice_column`]' \
        '--tty;*,[`_module_os_tty`]' \
        '--user;*,[`_module_os_user`]' \

}

_choice_column() {
    cat <<-'EOF'
%cpu	cpu utilization of the process in \"##.#\" format
%mem	ratio of the process's resident set size  to the physical memory on the machine
args	command with all its arguments as a string
blocked	mask of the blocked signals
bsdstart	time the command started
bsdtime	accumulated cpu time, user + system
c	processor utilization
caught	mask of the caught signals
cgname	display name of control groups to which the process belongs
cgroup	display control groups to which the process belongs
class	scheduling class of the process
cls	scheduling class of the process
cmd	see args
comm	command name
command	See args
cp	per-mill (tenths of a percent) CPU usage
cputime	cumulative CPU time, \"[DD-]hh:mm:ss\" format
cputimes	cumulative CPU time in seconds
drs	data resident set size
egid	effective group ID number of the process as a decimal integer
egroup	effective group ID of the process
eip	instruction pointer
esp	stack pointer
etime	elapsed time since the process was started, in the form [[DD-]hh:]mm:ss
etimes	elapsed time since the process was started, in seconds
euid	effective user ID (alias uid)
euser	effective user name
exe	path to the executable
f	flags associated with the process, see the PROCESS FLAGS section
fgid	filesystem access group ID
fgroup	filesystem access group ID
flag	see f
flags	see f
fname	first 8 bytes of the base name of the process's executable file
fuid	filesystem access user ID
fuser	filesystem access user ID
gid	see egid
group	see egroup
ignored	mask of the ignored signals
ipcns	Unique inode number describing the namespace the process belongs to
label	security label
lstart	time the command started
lsession	displays the login session identifier of a process
luid	displays Login ID associated with a process
lwp	light weight process (thread) ID of the dispatchable entity
lxc	The name of the lxc container within which a task is running
machine	displays the machine name for processes assigned to VM or container
maj_flt	The number of major page faults that have occurred with this process
min_flt	The number of minor page faults that have occurred with this process
mntns	Unique inode number describing the namespace the process belongs to
netns	Unique inode number describing the namespace the process belongs to
ni	nice value
nice	see ni
nlwp	number of lwps (threads) in the process
numa	The node associated with the most recently used processor
nwchan	address of the kernel function where the process is sleeping
ouid	displays the Unix user identifier of the owner of the session of a process
pcpu	see %cpu
pending	mask of the pending signals
pgid	process group ID or, equivalently, the process ID of the process group leader
pgrp	see pgid
pid	a number representing the process ID
pidns	Unique inode number describing the namespace the process belongs to
pmem	see %mem
policy	scheduling class of the process
ppid	parent process ID
pri	priority of the process
psr	processor that process is currently assigned to
rgid	real group ID
rgroup	real group name
rss	resident set size, the non-swapped physical memory that a task has used
rssize	see rss
rsz	see rss
rtprio	realtime priority
ruid	real user ID
ruser	real user ID
s	minimal state display
sched	scheduling policy of the process
seat	displays the identifier associated with all hardware devices assigned to a specific workplace
sess	session ID or, equivalently, the process ID of the session leader
sgi_p	processor that the process is currently executing on
sgid	saved group ID
sgroup	saved group name
sid	see sess
sig	see pending
sigcatch	see caught
sigignore	see ignored
sigmask	see blocked
size	approximate amount of swap space that would be required if the process were to be swapped out
slice	displays the slice unit which a process belongs to
spid	see lwp
stackp	address of the bottom (start) of stack for the process
start	time the command started
start_time	starting time or date of the process
stat	multi-character process state
state	see s
stime	see start_time
suid	saved user ID
supgid	group ids of supplementary groups, if any
supgrp	group names of supplementary groups, if any
suser	saved user name
svgid	see sgid
svuid	see suid
sz	size in physical pages of the core image of the process
tgid	a number representing the thread group to which a task belongs
thcount	see nlwp
tid	the unique number representing a dispatchable entity
time	cumulative CPU time, \"[DD-]HH:MM:SS\" format
times	cumulative CPU time in seconds
tname	controlling tty (terminal)
tpgid	ID of the foreground process group on the tty (terminal) that the process is connected to
trs	text resident set size
tt	controlling tty (terminal)
tty	controlling tty (terminal)
ucmd	see comm
ucomm	see comm
uid	see euid
uname	see euser
unit	displays unit which a process belongs to
user	see euser
userns	Unique inode number describing the namespace the process belongs to
utsns	Unique inode number describing the namespace the process belongs to
uunit	displays user unit which a process belongs to
vsize	see vsz
vsz	virtual memory size of the process in KiB
wchan	name of the kernel function in which the process is sleeping
EOF
}
