#!/usr/bin/env python3
from functools import partial
import math

from geometry_msgs.msg import Twist
from my_interfaces.msg import Turtle
from my_interfaces.msg import TurtleArray
from my_interfaces.srv import CatchTurtle
import rclpy
from rclpy.node import Node
from turtlesim.msg import Pose
from turtlesim.srv import SetPen


class TurtleControllerNode(Node):

    def __init__(self):
        super().__init__('turtle_controller')
        self.declare_parameter('catch_closest_turtle_first', True)
        self.declare_parameter('max_linear_speed', 2.0)

        self.catch_closest_turtle_first_ = self.get_parameter(
            'catch_closest_turtle_first').value
        self.max_linear_speed_ = self.get_parameter(
            'max_linear_speed').value
        self.turtle_to_catch_: Turtle = None
        self.pose_: Pose = None
        self.pen_disabled_ = False
        self.catch_request_pending_ = False
        self.catch_request_name_ = None

        self.cmd_vel_publisher_ = self.create_publisher(
            Twist, '/turtle1/cmd_vel', 10)
        self.pose_subscriber_ = self.create_subscription(
            Pose, '/turtle1/pose', self.callback_pose, 10)
        self.alive_turtles_subscriber_ = self.create_subscription(
            TurtleArray, 'alive_turtles', self.callback_alive_turtles, 10)
        self.catch_turtle_client_ = self.create_client(CatchTurtle, 'catch_turtle')
        self.set_pen_client_ = self.create_client(SetPen, '/turtle1/set_pen')
        self.control_loop_timer_ = self.create_timer(0.01, self.control_loop)

    def disable_pen(self):
        if not self.set_pen_client_.service_is_ready():
            return
        request = SetPen.Request()
        request.off = True
        self.set_pen_client_.call_async(request)
        self.pen_disabled_ = True

    def callback_pose(self, pose: Pose):
        self.pose_ = pose
        if not self.pen_disabled_:
            self.disable_pen()

    def callback_alive_turtles(self, msg: TurtleArray):
        alive_turtle_names = {turtle.name for turtle in msg.turtles}
        if self.catch_request_pending_:
            if self.catch_request_name_ in alive_turtle_names:
                return
            self.catch_request_pending_ = False
            self.catch_request_name_ = None

        if len(msg.turtles) > 0:
            if self.pose_ is None:
                return
            if self.catch_closest_turtle_first_:
                closest_turtle = None
                closest_turtle_distance = None

                for turtle in msg.turtles:
                    dist_x = turtle.x - self.pose_.x
                    dist_y = turtle.y - self.pose_.y
                    distance = math.sqrt(dist_x * dist_x + dist_y * dist_y)
                    if closest_turtle is None or distance < closest_turtle_distance:
                        closest_turtle = turtle
                        closest_turtle_distance = distance
                self.turtle_to_catch_ = closest_turtle
            else:
                self.turtle_to_catch_ = msg.turtles[0]

    def control_loop(self):
        if (self.pose_ is None or self.turtle_to_catch_ is None
                or self.catch_request_pending_):
            return

        dist_x = self.turtle_to_catch_.x - self.pose_.x
        dist_y = self.turtle_to_catch_.y - self.pose_.y
        distance = math.sqrt(dist_x * dist_x + dist_y * dist_y)

        cmd = Twist()

        if distance > 0.5:
            cmd.linear.x = min(self.max_linear_speed_, 2 * distance)

            goal_theta = math.atan2(dist_y, dist_x)
            diff = goal_theta - self.pose_.theta
            if diff > math.pi:
                diff -= 2 * math.pi
            elif diff < -math.pi:
                diff += 2 * math.pi
            cmd.angular.z = 6 * diff
        else:
            cmd.linear.x = 0.0
            cmd.angular.z = 0.0
            if self.catch_turtle_client_.service_is_ready():
                self.catch_request_pending_ = True
                self.catch_request_name_ = self.turtle_to_catch_.name
                self.call_catch_turtle_service(self.catch_request_name_)
                self.turtle_to_catch_ = None

        self.cmd_vel_publisher_.publish(cmd)

    def call_catch_turtle_service(self, turtle_name):
        request = CatchTurtle.Request()
        request.name = turtle_name
        future = self.catch_turtle_client_.call_async(request)
        future.add_done_callback(
            partial(self.callback_call_catch_turtle_service, turtle_name=turtle_name))

    def callback_call_catch_turtle_service(self, future, turtle_name):
        response: CatchTurtle.Response = future.result()
        if not response.success:
            self.catch_request_pending_ = False
            self.catch_request_name_ = None
            self.get_logger().error(
                'Turtle ' + turtle_name + ' could not be removed')


def main(args=None):
    rclpy.init(args=args)
    node = TurtleControllerNode()
    rclpy.spin(node)
    rclpy.shutdown()


if __name__ == '__main__':
    main()
