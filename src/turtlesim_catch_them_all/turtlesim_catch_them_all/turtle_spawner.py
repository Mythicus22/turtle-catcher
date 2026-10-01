#!/usr/bin/env python3
from functools import partial
import math
import random

from my_interfaces.msg import Turtle
from my_interfaces.msg import TurtleArray
from my_interfaces.srv import CatchTurtle
import rclpy
from rclpy.node import Node
from turtlesim.srv import Kill
from turtlesim.srv import Spawn


class TurtleSpawnerNode(Node):

    def __init__(self):
        super().__init__('turtle_spawner')
        self.declare_parameter('turtle_name_prefix', 'turtle')
        self.declare_parameter('spawn_frequency', 1.0)

        self.declare_parameter('max_alive_turtles', 10)
        self.declare_parameter('log_spawned_turtles', True)

        self.turtle_name_prefix_ = self.get_parameter('turtle_name_prefix').value
        self.spawn_frequency_ = self.get_parameter('spawn_frequency').value
        self.max_alive_turtles_ = self.get_parameter('max_alive_turtles').value
        self.log_spawned_turtles_ = self.get_parameter(
            'log_spawned_turtles').value
        self.turtle_counter_ = 0
        self.alive_turtles_ = []
        self.alive_turtles_publisher_ = self.create_publisher(
            TurtleArray, 'alive_turtles', 10)
        self.spawn_client_ = self.create_client(Spawn, '/spawn')
        self.kill_client_ = self.create_client(Kill, '/kill')
        self.catch_turtle_service_ = self.create_service(
            CatchTurtle, 'catch_turtle', self.callback_catch_turtle)
        self.spawn_turtle_timer_ = self.create_timer(
            1.0/self.spawn_frequency_, self.spawn_new_turtle)

    def callback_catch_turtle(self, request: CatchTurtle.Request, response: CatchTurtle.Response):
        if not any(turtle.name == request.name for turtle in self.alive_turtles_):
            response.success = False
            return response
        self.call_kill_service(request.name)
        response.success = True
        return response

    def publish_alive_turtles(self):
        msg = TurtleArray()
        msg.turtles = self.alive_turtles_
        self.alive_turtles_publisher_.publish(msg)

    def spawn_new_turtle(self):
        if len(self.alive_turtles_) >= self.max_alive_turtles_:
            return
        self.turtle_counter_ += 1
        name = self.turtle_name_prefix_ + str(self.turtle_counter_)
        x = random.uniform(0.0, 11.0)
        y = random.uniform(0.0, 11.0)
        theta = random.uniform(0.0, 2*math.pi)
        self.call_spawn_service(name, x, y, theta)

    def call_spawn_service(self, turtle_name, x, y, theta):
        if not self.spawn_client_.service_is_ready():
            self.get_logger().warn('Spawn service not ready, skipping.')
            return

        request = Spawn.Request()
        request.x = x
        request.y = y
        request.theta = theta
        request.name = turtle_name

        future = self.spawn_client_.call_async(request)
        future.add_done_callback(
            partial(self.callback_call_spawn_service, request=request))

    def callback_call_spawn_service(self, future, request: Spawn.Request):
        response: Spawn.Response = future.result()
        if response.name != '':
            if self.log_spawned_turtles_:
                self.get_logger().info('New alive turtle: ' + response.name)
            new_turtle = Turtle()
            new_turtle.name = response.name
            new_turtle.x = request.x
            new_turtle.y = request.y
            new_turtle.theta = request.theta
            self.alive_turtles_.append(new_turtle)
            self.publish_alive_turtles()

    def call_kill_service(self, turtle_name):
        if not self.kill_client_.service_is_ready():
            self.get_logger().warn('Kill service not ready, skipping.')
            return

        request = Kill.Request()
        request.name = turtle_name

        future = self.kill_client_.call_async(request)
        future.add_done_callback(
            partial(self.callback_call_kill_service, turtle_name=turtle_name))

    def callback_call_kill_service(self, future, turtle_name):
        for (i, turtle) in enumerate(self.alive_turtles_):
            if turtle.name == turtle_name:
                del self.alive_turtles_[i]
                self.publish_alive_turtles()
                break


def main(args=None):
    rclpy.init(args=args)
    node = TurtleSpawnerNode()
    rclpy.spin(node)
    rclpy.shutdown()


if __name__ == '__main__':
    main()
