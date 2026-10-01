#!/usr/bin/env python3
from functools import partial
from select import select
import sys
import termios
import threading
import time
import tty

from geometry_msgs.msg import Twist
from my_interfaces.msg import TurtleArray
from my_interfaces.srv import CatchTurtle
import rclpy
from rclpy.node import Node
from turtlesim.msg import Pose
from turtlesim.srv import SetPen
from turtlesim.srv import TeleportAbsolute


class ManualControllerNode(Node):

    def __init__(self):
        super().__init__('manual_controller')
        self.declare_parameter('manual_linear_speed', 2.0)
        self.declare_parameter('manual_angular_speed', 2.5)
        self.declare_parameter('catch_distance', 0.5)
        self.declare_parameter('key_hold_timeout', 0.6)

        self.manual_linear_speed_ = self.get_parameter(
            'manual_linear_speed').value
        self.manual_angular_speed_ = self.get_parameter(
            'manual_angular_speed').value
        self.catch_distance_ = self.get_parameter('catch_distance').value
        self.key_hold_timeout_ = self.get_parameter(
            'key_hold_timeout').value

        self.pose_: Pose = None
        self.alive_turtles_ = []
        self.pen_disabled_ = False
        self.key_activity_ = {}
        self.game_over_ = False
        self.resetting_ = False
        self.pending_catch_ = False
        self.pending_catch_name_ = None
        self.reset_target_names_ = set()
        self.restart_requested_ = False
        self.quit_requested_ = False
        self.score_ = 0
        self.round_number_ = 1
        self.running_ = True
        self.raw_terminal_settings_ = None
        self.input_stream_ = None
        self.terminal_lock_ = threading.Lock()

        self.cmd_vel_publisher_ = self.create_publisher(
            Twist, '/turtle1/cmd_vel', 10)
        self.pose_subscriber_ = self.create_subscription(
            Pose, '/turtle1/pose', self.callback_pose, 10)
        self.alive_turtles_subscriber_ = self.create_subscription(
            TurtleArray, 'alive_turtles', self.callback_alive_turtles, 10)
        self.catch_turtle_client_ = self.create_client(
            CatchTurtle, 'catch_turtle')
        self.set_pen_client_ = self.create_client(SetPen, '/turtle1/set_pen')
        self.teleport_client_ = self.create_client(
            TeleportAbsolute, '/turtle1/teleport_absolute')
        self.control_loop_timer_ = self.create_timer(0.05, self.control_loop)

        self.print_instructions()
        self.keyboard_thread_ = threading.Thread(
            target=self.keyboard_loop, daemon=True)
        self.keyboard_thread_.start()

    def print_instructions(self):
        print('\n' + '=' * 60, flush=True)
        print('TURTLE CATCHER - MANUAL MEMORY MODE', flush=True)
        print('=' * 60, flush=True)
        print('Catch the oldest spawned turtle first.', flush=True)
        print(
            'Controls: W forward | S reverse | A/D rotate | Space stop',
            flush=True)
        print('Press Q to end the current round.', flush=True)
        print('Score: 0 | Targets alive: 0', flush=True)
        print('=' * 60 + '\n', flush=True)

    def enable_raw_terminal(self):
        with self.terminal_lock_:
            if self.raw_terminal_settings_ is None:
                self.raw_terminal_settings_ = termios.tcgetattr(
                    self.input_stream_)
                tty.setcbreak(self.input_stream_.fileno())

    def disable_raw_terminal(self):
        with self.terminal_lock_:
            if self.raw_terminal_settings_ is not None:
                termios.tcsetattr(
                    self.input_stream_, termios.TCSADRAIN,
                    self.raw_terminal_settings_)
                self.raw_terminal_settings_ = None

    def open_terminal_input(self):
        try:
            terminal = open('/dev/tty', 'r')
            if terminal.isatty():
                return terminal
            terminal.close()
        except OSError:
            pass
        if sys.stdin.isatty():
            return sys.stdin
        return None

    def keyboard_loop(self):
        try:
            self.input_stream_ = self.open_terminal_input()
            if self.input_stream_ is None:
                print(
                    'Manual controls need a terminal input device. '
                    'Run this launch command from an interactive terminal.',
                    flush=True)
                while self.running_:
                    time.sleep(0.5)
                return
            self.enable_raw_terminal()
            while self.running_:
                if self.game_over_ and not self.resetting_:
                    self.disable_raw_terminal()
                    print('\nPlay again? [y/n]: ', end='', flush=True)
                    answer = self.input_stream_.readline().strip().lower()
                    if answer == 'y':
                        self.game_over_ = False
                        self.restart_requested_ = True
                        self.enable_raw_terminal()
                    elif answer == 'n':
                        self.quit_requested_ = True
                        break
                    else:
                        print('Please enter y or n.', flush=True)
                    continue

                ready, _, _ = select([self.input_stream_], [], [], 0.1)
                if ready:
                    key = self.input_stream_.read(1).lower()
                    if key == 'q':
                        self.finish_round('Round ended by player.')
                    elif key == ' ':
                        self.key_activity_.clear()
                    elif key in ('w', 's', 'a', 'd'):
                        now = time.monotonic()
                        if key in ('w', 's'):
                            opposite_key = 's' if key == 'w' else 'w'
                        else:
                            opposite_key = 'd' if key == 'a' else 'a'
                        self.key_activity_.pop(opposite_key, None)
                        self.key_activity_[key] = now
        finally:
            self.disable_raw_terminal()
            if self.input_stream_ is not None and self.input_stream_ is not sys.stdin:
                self.input_stream_.close()

    def callback_pose(self, pose: Pose):
        self.pose_ = pose
        if self.pen_disabled_ or not self.set_pen_client_.service_is_ready():
            return
        request = SetPen.Request()
        request.off = True
        self.set_pen_client_.call_async(request)
        self.pen_disabled_ = True

    def callback_alive_turtles(self, msg: TurtleArray):
        self.alive_turtles_ = list(msg.turtles)
        alive_names = {turtle.name for turtle in self.alive_turtles_}
        if self.resetting_ and not self.reset_target_names_ & alive_names:
            self.resetting_ = False
            self.reset_target_names_.clear()
            print('\nNew round ready. Remember the spawn order!\n', flush=True)

        if self.pending_catch_ and self.pending_catch_name_ not in alive_names:
            self.pending_catch_ = False
            self.pending_catch_name_ = None
            print(
                'Score: %d | Targets alive: %d' %
                (self.score_, len(self.alive_turtles_)), flush=True)

    def control_loop(self):
        if self.quit_requested_:
            self.running_ = False
            self.stop_turtle()
            rclpy.shutdown()
            return

        if self.restart_requested_:
            self.restart_requested_ = False
            self.restart_round()

        if self.pose_ is None or self.game_over_ or self.resetting_:
            self.stop_turtle()
            return

        self.publish_manual_command()
        self.check_for_catch()

    def publish_manual_command(self):
        command = Twist()
        now = time.monotonic()
        if self.is_key_active('w', now):
            command.linear.x = self.manual_linear_speed_
        elif self.is_key_active('s', now):
            command.linear.x = -self.manual_linear_speed_
        if self.is_key_active('a', now):
            command.angular.z = self.manual_angular_speed_
        elif self.is_key_active('d', now):
            command.angular.z = -self.manual_angular_speed_
        self.cmd_vel_publisher_.publish(command)

    def is_key_active(self, key, now):
        last_activity = self.key_activity_.get(key)
        return (last_activity is not None
                and now - last_activity <= self.key_hold_timeout_)

    def stop_turtle(self):
        self.cmd_vel_publisher_.publish(Twist())

    def check_for_catch(self):
        if self.pending_catch_ or not self.alive_turtles_ or self.pose_ is None:
            return

        collided_turtle = None
        closest_distance = None
        for turtle in self.alive_turtles_:
            distance_x = turtle.x - self.pose_.x
            distance_y = turtle.y - self.pose_.y
            distance = (distance_x ** 2 + distance_y ** 2) ** 0.5
            if distance <= self.catch_distance_ and (
                    closest_distance is None or distance < closest_distance):
                collided_turtle = turtle
                closest_distance = distance

        if collided_turtle is None:
            return

        oldest_turtle = self.alive_turtles_[0]
        if collided_turtle.name != oldest_turtle.name:
            self.finish_round('Wrong turtle. The oldest target was not caught.')
            return

        if not self.catch_turtle_client_.service_is_ready():
            return
        self.pending_catch_ = True
        self.pending_catch_name_ = oldest_turtle.name
        request = CatchTurtle.Request()
        request.name = oldest_turtle.name
        future = self.catch_turtle_client_.call_async(request)
        future.add_done_callback(
            partial(self.callback_catch_turtle, name=oldest_turtle.name))

    def callback_catch_turtle(self, future, name):
        response = future.result()
        if not response.success:
            self.pending_catch_ = False
            self.pending_catch_name_ = None
            self.finish_round('The target could not be removed.')
            return
        self.score_ += 1
        print('\nCorrect catch! Score: %d' % self.score_, flush=True)

    def finish_round(self, message):
        if self.game_over_:
            return
        self.game_over_ = True
        self.key_activity_.clear()
        self.stop_turtle()
        print('\n' + message, flush=True)
        print('Round %d score: %d' % (self.round_number_, self.score_), flush=True)

    def restart_round(self):
        self.round_number_ += 1
        self.score_ = 0
        self.game_over_ = False
        self.key_activity_.clear()
        self.pending_catch_ = False
        self.pending_catch_name_ = None
        self.reset_target_names_ = {turtle.name for turtle in self.alive_turtles_}
        self.resetting_ = bool(self.reset_target_names_)

        if self.catch_turtle_client_.service_is_ready():
            for turtle_name in self.reset_target_names_:
                request = CatchTurtle.Request()
                request.name = turtle_name
                self.catch_turtle_client_.call_async(request)

        if self.teleport_client_.service_is_ready():
            request = TeleportAbsolute.Request()
            request.x = 5.544445
            request.y = 5.544445
            request.theta = 0.0
            self.teleport_client_.call_async(request)

        if not self.resetting_:
            print('\nNew round ready. Remember the spawn order!\n', flush=True)

    def destroy_node(self):
        self.running_ = False
        self.disable_raw_terminal()
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = ManualControllerNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
