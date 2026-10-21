#!/usr/bin/env bash
# 10/13 master queue z1 (03:00): the remaining work of queues u5, v1, w2 and y1, one part after another, in this
# order: E2 read (generated validation) -> cross-benchmark repetitions -r1 -> prompt-profile evaluation ->
# fresh-task blocks Q32..Q40 -> E1 (frozen Skills on generated tasks) -> further cross-benchmark repetitions.
# Each part keeps its own snapshot, inputs, arm lists and retry rule; a part that halts does not stop the next
# part. Nothing is resumed; NO test data.
D=/root/fivebench-g-20261013-queue-z1
L=/root/fivebench-g-20261013-active
part() { name=$1; shift; echo "$(date -Iseconds) part $name start"; bash "$@" >> $L-$name.log 2>&1; echo "$(date -Iseconds) part $name end (exit $?)"; }
part v1b $D/v1b.sh
part w3 $D/w3.sh 1
part y1b $D/y1b.sh
part u6 $D/u6.sh
part v1c $D/v1c.sh
part w3 $D/w3.sh 3
echo "$(date -Iseconds) Z1-EXIT"
