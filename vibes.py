import time
import datetime
import atexit
import Queue as queue
import threading
import RPi.GPIO as GPIO
from zstd import LoggableApp, LoggableThread


GPIO_PIN = 18


class RunningCheckThread(LoggableThread):
    def __init__(self, queue, shutdown, verbose=False, *args, **kwargs):
        self.queue = queue
        self.shutdown = shutdown
        self.verbose = verbose
        self.strfmt = kwargs.pop("strfmt", "%Y-%m-%d %H:%M:%S")
        super(RunningCheckThread, self).__init__(*args, **kwargs)
        self._status = False
        self.started = self.finished = datetime.datetime.now()

    @property
    def status(self):
        return self._status

    @status.setter
    def status(self, value):
        if value != self._status:
            self._status = value
            self.show()
            if self._status:
                self.started = datetime.datetime.now()
            else:
                self.finished = datetime.datetime.now()
                self.notify()

    @property
    def now(self):
        timestamp = datetime.datetime.now()
        return timestamp.strftime(self.strfmt)

    @property
    def elapsed(self):
        return (self.finished - self.started)

    def notify(self):
        self.logger.info("Vibration ceased : %s elapsed", self.elapsed)

    def show(self):
        msg = "{} Transition => {}".format(self.now, self.status)
        self.logger.debug(msg)

    def run(self):
        while not self.shutdown.is_set():
            try:
                self.status = self.queue.get(timeout=1)
            except queue.Empty:
                pass
            self.shutdown.wait(1)


class PollingThread(threading.Thread):
    def __init__(self, pin, queue, shutdown, verbose=False, *args, **kwargs):
        self.pin = pin
        self.queue = queue
        self.shutdown = shutdown
        self.verbose = verbose
        self.frequency = kwargs.pop("frequency", 100)
        self.magnitude = kwargs.pop("magnitude", 20)
        super(PollingThread, self).__init__(*args, **kwargs)
        self.gather = threading.Event()
        self.counts = [0, 0]

    @property
    def status(self):
        return self.counts[0] < (self.counts[1] * self.magnitude)

    def update(self):
        self.gather.set()
        timer = threading.Timer(1, self.update)
        timer.start()

    def show(self):
        # if self.verbose:
        #     print("{} / {} => {}".format(self.counts[0], self.counts[1],
        #                                  self.status))
        pass

    def run(self):
        # print("running")
        timer = threading.Timer(1, self.update)
        timer.start()
        while not self.shutdown.is_set():
            self.gather.clear()
            # reset counts
            self.counts = [0, 0]
            while not self.gather.is_set():
                value = GPIO.input(self.pin)
                self.counts[value] += 1
                # print('on' if value else 'off')
                time.sleep(1.0 / self.frequency)
                if self.shutdown.is_set():
                    break
            self.queue.put(self.status)
            self.show()
            # print("{} / {} => {}".format(self.counts[0], self.counts[1],
            #                              self.status))
        

class VibesApp(LoggableApp):
    def __init__(self, pin, *args, **kwargs):
        self.pin = pin
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.pin, GPIO.IN)
        atexit.register(self.cleanup)
        super(VibesApp, self).__init__(*args, **kwargs)

    def cleanup(self):
        # print("cleaning up")
        GPIO.cleanup()

    def poll(self):
        pass

    def run(self):
        
        # print("Starting up")
        self.logger.info("Starting up")
        shutdown = threading.Event()
        work_queue = queue.Queue()

        checker = RunningCheckThread(work_queue, shutdown, verbose=True)
        checker.start()

        poller = PollingThread(GPIO_PIN, work_queue, shutdown)
        poller.start()

        checker.join()
        poller.join()

        try:
            while not shutdown.is_set():
                # value = GPIO.input(self.pin)
                # print("value = {}".format(value))
                # time.sleep(0.1)
                # status = work_queue.get(timeout=1)
                # print(status)
                shutdown.wait(60)
        except KeyboardInterrupt:
            shutdown.set()


app = VibesApp(GPIO_PIN)
app.run()
