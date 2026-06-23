# Fastidious Farmer Algorithms (FFA)

Matthew Fischer, Nikifor Bliznashki and Brandon Levin

March 9, 2006

## 1 Introduction

Approximately 10,000 years ago, civilization began in the Fertile Crescent of Mesopotamia around the river valleys of the Euphrates and the Tiger rivers. It was agriculture that allowed these civilizations to prosper and the river water that allowed agriculture. The number of people in the world has grown significantly since then increasing the demand for food production. Agriculture has been forced to move away from water sources like rivers and valleys into the dryer regions across the globe. Artificial irrigation has thus become an essential element of any successful farming enterprise. For example, in Afghanistan, where 80 % of the population works in agriculture, good irrigation techniques can decrease costs and increase yields bolstering a growing economy. In this study, we consider “hand move” irrigation system which can be made cheap and effective for small farm plots. We consider the important sensitivities of the crops to both over and underwatering. Careful application is required in some soils where only a limited amount of water can be absorbed before runoff becomes a problem. All these consideration must be taken into account in developing a successful irrigation procedure.

## 2 Abstract

An effective irrigation algorithm is crucial to “hand move” irrigation systems. “Hand move” systems consist of easily movable aluminum pipes and sprinklers, and are typically used as a low-cost, low-scale watering system. However, without an effective design algorithm, the crops will either be watered improperly, resulting in a damaged harvest, or watered inefficiently, using up too much of the precious resources. Therefore, in this paper we focus on determining an algorithm for “hand move” irrigation systems that irrigates as uniformly as possible in the least amount of time. We analyzed this problem in three steps: physically characterizing the system, determining a method of evaluating various irrigation algorithms and testing the proposed irrigation algorithms to determine the most effective strategy.

Using fluid mechanics, we were able to determine that we could have at most three nozzles on the 20 meter pipe while maintaining water pressure. We modeled our sprinkler system after the Rain Bird 70H 1" impact sprinkler which works at the desired pressure and has approximately a .6 cm diameter. Combining experimentally determined data and dynamical analysis, we determine the radius of the sprinkler to be 19.5 meters. Researchers have proposed several different methods of modeling the water distribution pattern about a sprinkler. For our purposes, we consider a Triangular Distribution and an Exponential Distribution. We discuss the strengths and weaknesses of these models.

The farmer will be weighing costs of labor, time, stability, and uniformity in choosing an irrigation method. We did not consider any schemes which did not water all areas of the field at least 2 cm/hr or watered areas more than .75 cm/hr. The largest cost in terms of time and labor will be in moving the pipe. Thus, we looked for small number of moves, which still gave the desired time and stability. Of these configurations, a computer analysis would tell us which one was most uniform.

For various situations, we propose our optimal solutions. The basis of all the patterns were triangular and rectangular lattices which were analyzed in generality in a paper. We then crafted three patterns to fit carefully on the field to maximize application to the difficult edges and corners. For perfectly calm conditions and a perfectly level field, it is possible to water the field with only a couple of moves, the Lazy Farmer configuration. However, this approach is very unstable, and even weak wind would leave parts of the field dry. We show that with three moves, you gain little in stability and so feel that four positions will be the best for those concerned with variable conditions. The “Creative Farmer” triangular lattice gives both stability and uniformity. The extra time will be warranted because of its ability to adapt. We obtain even more stability using the “Conservative Farmer” model, but this comes at the price of decrease in uniformity. These three patterns provide a suitable solution for most real-world configurations.

## 3 Description of Problem

In this problem, we consider a cheap but effective means of agricultural irrigation, the “hand move” system. The goal is to irrigate a field which is 30 m by 80 m as uniformly as possible while minimizing labor/time required. We are given the following basic equipment:

- Pipes of $10 \mathrm{~cm}$ diameter with rotating spray nozzles of .6 cm diameter  
- Nozzles are raised about 1 meter from the pipe and can spray at angles ranging from 20 to 30 degrees  
• Total length of the pipe is 20 meters  
- A water source with a pressure of 420 kilo-Pascal's and a flow rate of $150 \mathrm{~L} / \mathrm{min}$

Different crops and different soils respond best to certain application rates and total water application. In this problem, we consider the following guidelines:

- No part of the field should receive more than .75 cm/hour  
- Every part of the field should recieve at least 2 cm every four days  
- Significant over-watering from non-uniform distributions should be avoided

The real world has many complicated variables to consider. In order to simplify the problem, we make some basic assumptions about conditions. In general, we feel these assumptions are justified in the common farming experience.

- Sprinklers are in working order and standard production. They rotate 360 degrees spraying uniformly with respect to rotational symmetry.  
- The soil is approximately uniform and the terrain flat.  
- Wind is considered only inte terms of stability. We will explore this in more detail after the basic models have been established.

- We assume that we can place a water supply pipe through the field either along its width or length that will have multiple connection spots for the movable pipes.  
- For such a small field, we assume that any move will require approximately equal time so we need only minimize the total number of moves $M_T$ .  
- We recognize that in particularly arid areas evaporation will take place reducing the total water application, but assume this will result in no more than a $5\%$ loss.  
- We also ignore rainfall affects assuming those can be accounted for by delaying the scheduled waterings.

## Definitions and Notation

Let $D$ be a distribution of sprinklers. This includes placement of sprinklers on the pipe and the arrangement throughout the field. We often want to consider the rate of accumulation over a region $R$ . In evaluating a set-up, we will be interested in a couple important quantities

$M_{T}(D) = \#$ of total moves required by the farmer for a distribution

Aver(D, R) = the average application rate over the region R

$Std(D, R) = \text{the deviation from the mean rate of application over a region}$

$Max(D, R) = \text{the maximum rate of application over the region } R$

$Min(D,R)=$ the minimum rate of application over the region $R$

## 4 Capacity of Pipe and Resulting Pressure/Radii

## Watch out for the Rain Bird

Congratulations! You just purchased a set of Rain Bird 70H 1" Brass Impact Sprinklers. The 6 mm nozzle will work nicely with your shiny new 20 m Aluminium tube. The pressure range of your water source fits in the recommended range for the 70H sprinkler. Now let's see what this baby can do.

We will derive the exit velocity, flow and radius for a sprinkler in our conditions and show it agrees with the Rain Bird model. We will assume laminar flow and use Bernoulli's equation:

$$
P _ {1} + \frac {1}{2} \rho v _ {1} ^ {2} + \rho g y _ {1} = P _ {2} + \frac {1}{2} \rho v _ {2} ^ {2} + \rho g y _ {2}.
$$

where $P_{i}$ is the absolute pressure, $\rho$ is the density of water, $v_{i}$ is velocity, $g$ is gravitational constant and $y_{i}$ is height. Because we assumed our field is flat, $y_{1} = y_{2}$ so the height of our source relative to our sprinklers does not affect the exit velocity. Solving for the exit velocity from the sprinkler $v_{2}$ we obtain:

$$
v _ {2} = \sqrt {\frac {2}{\rho} P + v _ {1} ^ {2}}
$$

where $P$ is the relative pressure. We must first find the velocity of water at our source.

$$
v _ {1} = \frac {1 5 0 L}{\min} \times \frac {1 \min}{6 0 s} \times \frac {1 m ^ {3}}{1 0 0 0 L} \times \frac {1}{\pi (. 0 5) ^ {2} m ^ {2}} = \frac {1}{\pi} m / s
$$

Plugging in the velocity of our source we obtain the exit velocity from our sprinkler

$$
v _ {2} = \sqrt {\frac {2}{1 0 0 0} 4 2 0 * 1 0 0 0 + \frac {1}{\pi^ {2}}}
$$

$$
v _ {2} \approx \sqrt {8 4 0} \approx 2 8. 9 8 m / s
$$

That's fast! It actually may be a little too fast. This exit velocity does not take into account friction in the pipes. We propose a sprinkler constant to take friction into account. The volume out of the sprinkler per second will be the velocity multiplied by the cross-sectional area of the sprinkler and a sprinkler constant. The formula for this relationship is the following:

$$
Q = C _ {s} A _ {c} \sqrt {\frac {2}{\rho} P}
$$

where Q is the discharge in cubic meters per second, $C_{s}$ is the sprinkler constant and $A_{c}$ is the cross-sectional area in meters squared. Using some pressure and discharge data from the Rain Bird website you find your sprinkler constant to be

$$
C _ {s} = \frac {Q}{A _ {c} \sqrt {\frac {2}{\rho P}}} = \frac {3 . 1 7 * \frac {1}{3 6 0 0}}{\pi (. 0 0 3 1 7 5) ^ {2} \sqrt {8 0 0}} \approx . 9 8 3.
$$

This value is acceptable and shows a very small loss due to friction in the system. This farmer probably reads a lot of message boards about sprinklers and irrigation systems and made an informed purchase. Now we can find our escape velocity with friction:

$$
v = . 9 8 3 \times 2 8. 9 3 \approx 2 8. 5 m / s
$$

Next we determine how many liters flow out of each sprinkler per minute. This will simply be the velocity multiplied by the area and then conversion to liters per minute:

$$
V o l u m e = 2 8. 5 \times \pi (. 0 0 3) ^ {2} \times \frac {1 0 0 0 L}{m ^ {3}} \times \frac {6 0 s}{m i n} = 4 8. 3 5 L / m i n
$$

We can therefore use up to three sprinklers without using more than 150L/min and dropping the pressure. If we use more than 3 sprinklers, the pressure will drop. To find the new pressure we will use the continuity principle which states that the volume of water flowing in equals the volume of water flowing out:

$$
A _ {s} v _ {s} = n A _ {N} v _ {N}
$$

where $A_{s}$ is the cross-sectional area of our source, $v_{s}$ is the velocity of water at our source, n is the number of sprinklers, $A_{N}$ is the cross-sectional area of the sprinkler nozzle, and $v_{N}$ is the velocity out of the sprinkler nozzle. Solving for $v_{N}$ we obtain:

$$
v _ {N} = \frac {r _ {s} ^ {2}}{n \pi r _ {N} ^ {2}} = \frac {(5 \times 1 0 ^ {- 2}) ^ {2}}{n \pi (3 \times 1 0 ^ {- 3}) ^ {2}} \approx \frac {8 8 m / s}{n}
$$

where $n > 3$ , $r_s$ is the radius of the pipe at the source and $r_N$ is the radius of the sprinkler nozzle.

If we were to use four sprinklers, the exit velocity would be 22 m/s and there would be a pressure drop. Using our previous equation for discharge, we find that the pressure for four sprinklers is 251.99 kPa. The Rain Bird website states that the pressure needs to be above 280 kPa. Out of respect for the people who maintain the Rain Bird website and the fact that too low of a pressure will result in a low degree of uniformity, we will say that we can operate a maximum of 3 sprinklers from our pipe at once.

## Kinematics Equations

Now that we have the exit velocity, our inquisitive farmer would like to understand what effects go into determining the radius of the water jet emitted from our sprinkler. Because water droplets are small and the escape velocity of our water droplets are above the terminal velocity of a reasonably sized water droplet, drag effects will have to be taken into account. Therefore, we will have the following differential equations for velocity in the x and y directions, respectively:

$$
\frac {d v _ {x}}{d t} = - k v _ {x}
$$

$$
\frac {d v _ {y}}{d t} = - g - k v _ {y}
$$

Solving these differential equations we obtain:

$$
y (t) = \frac {- g}{k} t + (\frac {v _ {0} k s i n \theta + g}{k ^ {2}}) (1 - e ^ {- k t}) + y _ {0}
$$

$$
x (t) = \frac {v _ {0} c o s \theta}{k} (1 - e ^ {- k t}) + x _ {0}
$$

We will use the following initial conditions in our model obtained from the Rain Bird website and from our calculations to determine the drag constant:

$$
y _ {0} = 1 m
$$

$$
x _ {0} = 0
$$

$$
v _ {0} = 1 m
$$

$$
\theta = 2 1 ^ {\circ}
$$

On the Rain Bird website, our farmer determined that the radius for our system will be approximately 19.5 m. Using this distance and the above initial conditions, we determined the drag constant numerically to be:

$$
k = 1. 2 0 3 1 4
$$

Using this drag constant, our farmer has an equation to understand how the radius of the water emitted by the sprinkler will be determined by the height and angle of the sprinkler. Although we will keep our sprinkler in its factory designed settings, our farmer could modify the sprinkler to adjust the radius if needed. Changing the angle or height too much, however, would likely lead to an nonuniform distribution due to the fact that the sprinkler was designed to spray properly with its factory settings. Thus we conclude this section by noting that we have a little flexibility in our 19.5 m radius.

## 5 Distribution of Water from Standard Rotational Sprinkler

While the sprinklers under consideration will cover a disk of radius 19.5 meters, the distribution over that area will not be uniform. Large droplets tend to travel farther, but the area near the perimeter is much larger than near the sprinkler head. Below, we discuss various models for this behavior based on empirical data.

## Triangular Model

In an article by Smajstrla et al., this group at the University of Florida proposed that the water distribution can be modeled approximately as a triangle. That is, the application rate falls linearly as a function of distance from the sprinkler head, disappearing outside the radius.

In three dimensions, this distribution becomes cone-shaped about the sprinkler. When we analyze the grid patterns, we will sum over numerous cones and analyze the resulting surface. At first, this model seems a bit naive but it has its merits. The fact that the highest application rate is at that sprinkler head makes sense based on the area underneath. For example, the amount of time the sprinkler spends shooting in the direction of say a $1 \, cm^{2}$ square near the perimeter is very small whereas a $1 \, cm^{2}$ next to the sprinkler head could be receiving water almost a fourth of the time. The smooth slope approximates, based on the fact that the water will spread once it hits the ground, by evening out to some extent what might have been initially non-uniform.

## Experimental/Exponential Decay Model

In the Journal of Irrigation and Drainage Engineering, Louie and Selker experimental test the performance of a Rain Bird 4.37-mm Nozzle. Noticeably, the distribution spikes within 2 meters of the sprinkler head, then maintains an approximately uniform rate before decaying near the edge of the radius. We used exponentials to fit a curve to this graph. We then scaled the width and the height of this function to correspond to the radius and water flow of our larger sprinkler. The equation and graph of the normalized function are given below:

$$
f (r) = \left(3 *. 0 0 2 6 7 * e ^ {-. 7 x} +. 0 0 2 6 7\right) * e ^ {- (x / 1 9. 5) ^ {2 0}}.
$$

Graph 2- Exponential Water Distribution

![](images/9581df4a02e8fb8791fcbcec06a6ec18a01f764f8323eb8f59e118285e45e868.jpg)

<details>
<summary>line chart</summary>

| Distance (m) | Rate (m/hr) |
| ------------ | ----------- |
| 0            | 0.01        |
| 5            | 0.003       |
| 10           | 0.0025      |
| 15           | 0.0025      |
| 20           | 0.001       |
</details>

To get the three-dimensional distribution, we then rotate the function about the z-axis by replacing r with $\sqrt{(x-a)^{2}+(y-b)^{2}}$ which give you a sprinkler centered at $(a,b)$ . We will use this function to aid in testing configurations. In some ways, this distribution is a worst case scenario because of the large peak about the sprinkler. The curve is based experimentally on where drops landed but does not take into account possible spread on landing.

## Comparison of Models

The Exponential Decay Model is certainly the more realistic of the two models. As we will show, it forces careful consideration of how long a sprinkler can be left on during the hour. Any configuration which is acceptable for this model will most likely work under the Triangular Model. When we work under the Triangle Model, we are given more flexibility in our arrangements. For crops which are sensitive to over-watering, one may want to carefully consider the Exponential Decay Model. If you are less worried about these consideration, the Triangular Model can be useful tool for evaluating uniformity. Of course, it would not be a bad idea to test actual individual sprinkler to determine what best fits the particular situation.

## Conclusions

Two important considerations arise out of these models which affect future analysis. Under the Exponential Model, notice that near the sprinkler head the application rate goes up to .01m/hr which is 10 cm/hr. In the problem, we constrained our rate of application to 7.5 cm/hr to avoid damage to the soil and crops. Thus, if we are to use the Exponential Model we will be constrained to set-ups where sprinklers run for less than the full 60 minutes every hour. In our methods section, we discuss several algorithms for minimizing the amount of inconvenience this constraint causes the farmer. A similar difficulty arises for the Triangular Model if we attempt to run three sprinklers at the same time. The best we can do for the sprinkler in the middle is to evenly space the sprinkler heads with two at the end. The distance of separation is then 10 meters. Scaling the triangle for the values of the Rain Bird (3.2 m³/hr, 19.5m radius), we get a peak height of about 8 cm/hr so at 10 meters you get 4 cm/hr. Then the middle sprinkler head would be receiving 16 cm/hr which is over twice as much as allowed. For either model, three sprinklers can only be run for a limited time every hour. Thus, most of our proposed solutions focus on two sprinklers running at a time separated by close to one radius distance.

## 6 Analysis of Standard Grid Patterns

We have so far determined that the radius will be between 19.5 meters and that we can put at most three sprinklers on the pipe without a loss of pressure and subsequent loss of standard distribution. In the final analysis, we will consider 19.5 meter radius. Here we analyze standard grid patterns using a distribution of height one and radius one. To maximize area covered, a single sprinkler is not advisable. To contrast the effects of varying distributions either triangular or exponential, all patterns will invoke overlapping sprinkler patterns. In most cases, researchers recommend $40 - 60\%$ overlap of radii to obtain the most uniform distribution which also tend to be the most stable under windy conditions (Eisenhauer). Symmetric designs which could cover our rectangular field include squares, rectangles and squares. We use the Triangular Distribution to evaluate the standard grid patterns with the goal of finding the ideal side lengths as a ratio of the radius. Under this model, the ideal rectangle is a square with side length $1.1(\text{radius})$ in terms of uniformity. A triangle grid pattern is shown to obtain better uniformity though with smaller spacing $(.85(\text{radius}))$ .

## Evaluation Methods

We have two primary concerns in evaluating the value of a grid pattern. The minimum value within the shape will determine the number of hours required to water the field so we must watch for too low a minimum value. We measure uniformity using a variation on the standard deviation of a distribution. In each case we consider a unit of the grid, that is, one square and one triangle and plot the distributions of all sprinklers that water that square. The average rate is defined by the following integral:

$$
A v e r (D, R) = \int_ {R} (D (x, y)) / A r e a (R)
$$

where $D(x,y)$ is the distribution and $R$ is the unit region. We can then define the standard deviation to be

$$
S t d (D, R) = \frac {1}{A r e a (R)} \int_ {R} (D (x, y) - A v e r (D, R)) ^ {2}.
$$

This parameter measures the amount of fluctuation towards extremese on the region. A large $Std(D,R)$ means water will be applied non-uniformly and could result in poor growth. To aid in assessing the extreme of the variation we also calculate the $Max(D,R)$ . The difference between $Max(D,R)$ and $Min(D,R)$ gives us a measure of how large the variation could be. At this point, we exclude the number of moves from the analysis. This factor will be brought in when we consider patterns on the field.

## Rectangular Grids

For each vertical separation $\{0, \ldots, 1.2\}$ within a reasonable range as recommended in research, we considered a range of possible horizontal separations. Generally, the standard deviation would go down and then back up defining a clear minimum value which for all configurations was around 1.1 along the horizontal. Table 2 in the Appendix shows the optimal lengths based on standard deviation. The best rectangular configurations turns out to be a square of sidelength $1.1(\text{radius})$ . The difference in maximum and minimum correlates closely with the standard deviation so there was no point in considering both.

## Triangular Grids

For the triangular lattice, it was important that we also model the surrounding triangles because the altitude of the triangle is smaller than the sidelength so these other sprinklers have a significant effect. Below is a graph of the standard deviation as a function of sidelength:

Triangle Lattice

![](images/fe98ac7be5158e19d28f149e3848a0b2e792a0ec0d5aa5690e327da7340ede58.jpg)

<details>
<summary>line chart</summary>

| Separation Distance (radii) | STD     |
| --------------------------- | ------- |
| 0.8                         | 0.0005  |
| 0.9                         | 0.001   |
| 1.0                         | 0.0025  |
| 1.1                         | 0.003   |
| 1.2                         | 0.002   |
</details>

We do not consider distances less than $.8(\text{radii})$ because significant overwatering would take place. Thus, the most uniform configuration is at the $.85(\text{radii})$ mark. This deviation beats that of the rectangular configuration. The Exponential Distribution gave similar results on the tests indicating that if possible triangular set-ups will yield better uniformity.

## 7 Proposed Irrigation Methods

Knowing how the sprinklers operate and what the resulting distribution of water is, we can proceed with the difficult task of designing our pipe network and watering schemes. We make the following assumptions:

- Water is distributed according to the exponential water distribution derived earlier.  
- No modifications to the sprinklers are permitted, and we would not have more than three sprinklers operational at the same time.  
- The efficiency of the sprinkler irrigation is at least 95%, meaning that 95% of the water reaches the ground and no more than 5% are lost due to evaporation and other factors.

\- There exists infrastructure that can supply water along the center of the field.

Our goal would be to design a system that provides at least 2cm of water at every point of the field every 4 days, and no more than 0.75 cm of water during an hour at any point. In addition, we would like the pattern of watering to be periodic with period of four days. We would compare the different systems using the following criteria

- Required number of movings of the pipes $M_T$  
• Hours of operation of the system  
- Stability with respect to factors like wind and equipment malfunctions  
• Uniformity of the irrigation

We begin with the following rather unpleasant observation that the amount of water falling right next to the sprinkler is 1 cm per hour, which means we cannot have a sprinkler operational for more than 45 minutes every hour. This implies that someone would have to come and stop the sprinklers 45 minutes after they have been turned on, and to turn them on again 15 minutes later. Since the pipes are equipped with valves that can easily be closed and opened, even under pressure, doing that would be an easy task that would consume no more than a few minutes. In addition, if a sprinkler is within the radius of another one, this will severely reduce the amount of time they can be operational, and thus we want to avoid it by positioning them at the ends on the 20 meter pipe.

Let us first take a look at the field:

![](images/c69635ac0e3bbaed10ca79d62b083282ae057ebb2b5a5abb427b0fd1740929bf.jpg)

<details>
<summary>text_image</summary>

A'
B'
C'
D'
E'
M
N
P
Q
A
B
C
D
E
</details>

Figure 7.1 Outlook of the field

Here we have divided the field into four 20m by 30m rectangular pieces, each of which is further subdivided into triangles by the two diagonals. It is clearly impossible to water the whole 30m by 80m using our pipe of length of 20 m and with radius of irrigation of 19.5 m, since we cannot water two points separated by more than $19.5m+20m+19.5m=59m$ . Therefore, we would have to move the pipe at least once, and since after 4 days the pipe should be in its initial position, we would have to move it twice per period. Therefore, our lower bound on $M_{T}$ is 2. It certainly would be nice to be able to achieve this minimum. Some insight of how this could be done can be obtained by drawing circles with radius 19.5 at the points $A, C, E, A', C'$ , and $E'$ , which can be seen at Figure 7.2

![](images/39345ef7d801c57aef3e584477dc0adc9567e56280d1841b389596abaeb326f5.jpg)

<details>
<summary>natural_image</summary>

Geometric diagram of six overlapping circles and squares (no text or symbols)
</details>

Figure 7.2 Covering the edges

We have to position the sprinklers in such a manner that in each circle there is at least one. This leads to the following line scheme with two movings:

## 7.1 The Case $M_T = 2$

Suppose we position the pipe in the following two places:

![](images/c99e4b35e1a38f5001dad293c565d4ca01ebd9196c010a040e89a595bc2441bc.jpg)

<details>
<summary>text_image</summary>

10m 20m 20m 20m 10m
</details>

Figure 7.3 The Lazy Farmer configuration

The furthest a point is from a sprinkler (denoted by a dot on the figure) is $\sqrt{10^{2}+15^{2}}=18.02$ meters, and these points are precisely A, C, E, $A^{\prime}, C^{\prime}$ , and $E^{\prime}$ on Figure 7.1. As we could see from our exponential water distribution graph, the amount of water falling at them would be 2.25mm/h, but since we operate a sprinkler for at most 45 minutes, the actual value would be 1.68mm/h. Thus, if we operate the system for 13 hours at each location, we would get a minimum of 2.18cm of water at every point, which accounts for more than 2cm of water everywhere when we subtract the water lost due to evaporation. Therefore, the total time the system would be operational is 26 hours, the pipes would have to be moved twice, and the amount of water used would be $(2)(26h)(45min/h)(48.35l/min)=113139l$ per period. If the watering was optimal, the required amount of water would be $(30m)(80m)(2cm)=48000l$ of water. Therefore, the water efficiency of our system would be 42%. As for uniformity, with methods developed earlier we calculate that the standart deviation is $1.7\times10^{-6}$ , which corresponds to a high degree of uniformity. However, this configuration has one major disadvantage: even a small change of 2 meters in the area covered (for instance due to wind, or decrease in pressure in the pipes) can result in distant points like A receiving no water. Therefore, this configuration, although very uniform and with minimal $M_{T}$ is not very stable. In order to deal with this, we consider the next configuration.

## 7.2 The case $M_{T}=3$

The best we can do after $M_{T}=2$ is to consider a configuration with three movings of the pipes. In addition, we want to have a smaller maximum distance between a point of the field and the nearest sprinkler, which we will denote by $d_{max}$ . Using a similar argument to the one from the previous case, the resulting configuration should look something like this:

![](images/31d22f94e2c2459aa2e7dcd05589d3c66c2c4e1f61c9a807217006a7a14ab5a8.jpg)

<details>
<summary>text_image</summary>

A'
B'
C'
D'
E'
M
N
P
Q
A
B
C
D
E
</details>

Figure 7.4 Configuration for $M_T = 3$

It can easily be shown that in a configuration like this one, $d_{max} \geq 16.5$ , and thus the gain when it comes to stability is very small. In addition, there is a huge increase in operational time and required amount of water: 39 hours and 169000l respectively. Therefore, the case $M_{T} = 3$ results in bad configurations.

## 7.3 The case $M_T = 4$

With the increase of number of times we can move the pipes, the complexity of the problem of positioning them in the best possible way increases very fast, making it nearly impossible to consider all configurations for $M_{T}=4$ . However, since we want to have a more stable configuration, we should have sprinklers close to the points A, $A'$ , E, and $E'$ . In addition, in order to keep uniformity of the watering, we should preserve some symmetry in the way we position the sprinklers. The earlier triangular and rectangular patterns can be successfully applied in this cae. The best way to reduce peaks in watering is to use a triangular pattern, like the one shown on Figure 7.5:

![](images/8dfec18aa9eb1e9bfabecbf7b37748d28074338c10f42f1b1555374230a42008.jpg)

<details>
<summary>natural_image</summary>

Pure geometric line diagram with dots and straight lines, no text or symbols present
</details>

Figure 7.5 Creative Farmer Layout

For the shown triangular layout, the sprinklers are positioned in the vertices of equilateral triangles with side 20m. After that, in order to minimize the instability, the leftmost pipe is translated 5 meters to the right, and the rightmost 5 meters to the left. Then $d_{max} \leq 14$ , which implies that this scheme would work well provided that the wind does not result in more than 25% deviation, which is true unless the wind is really strong. In addition, this layout has a standard deviation of $3.35 \times 10^{-6}$ , period of operation of 52 hours, and water consumption of 226000l per period.

Another way to minimize non-uniformity is to position the sprinklers in a rectangular pattern. Here is how it can be done:

![](images/4a54045cca1b42c8bcb87b721837118571ac91f6e182f3a722ecef6b54d57428.jpg)

<details>
<summary>text_image</summary>

5m
20m
5m
6m 23m 23m 23m 5m
</details>

Figure 7.6 Conservative Farmer Layout

In this case the distance from the sprinklers to the points on the sides are less than 12 meters, and the area between two pipe positions is within the radius of four sprinklers and thus would be watered no matter what the direction of the wind is. This implies that for this layout, the irrigation would be good provided that the wind doesn't alter the area covered by more than 7 meters, which is true unless there is a storm. The layout's standard deviation is $4.17 \times 10^{-6}$ , and the hours of operation and water consumption are the same as in the previous case.

## 7.4 The case $M_{T} > 4$

Considering that we have obtained relatively good stability, we might be interested in considering a configuration with more than 4 movings only if it saves drastically time or leads to high uniformity. However, since moving of the pipes takes a lot of time, and in addition we have observed how the standard deviation increases, even for the triangular configuration, we can conclude that the case $M_{T} > 4$ would not lead to a good layout.

<table><tr><td></td><td> $M_T$ </td><td>Uniformity</td><td>Stability</td><td>Hours of Operation</td><td>Water Used</td></tr><tr><td>Lazy</td><td>2</td><td>high</td><td>low</td><td>26</td><td>113000l</td></tr><tr><td>Creative</td><td>4</td><td>medium/high</td><td>medium/high</td><td>52</td><td>226000l</td></tr><tr><td>Conservative</td><td>4</td><td>medium</td><td>high</td><td>52</td><td>226000</td></tr></table>

## Numerical Analysis of Proposed Algorithms

Using the same criteria used to evaluate the standard grid patterns, we diagnosed the algorithms previously preposed on our 30m by 80m test field. We set up the field on a grid with endpoints $(0,0)$ , $(80,0)$ , $(0,30)$ and $(80,30)$ . This setup allows us to evaluate the entire field and take into account edge effects. The following four algorithms are the best performers of several algorithms we analyzed.

## Lazy Farmer Algorithm

For this algorithm we arranged the pipes in the following way. A diagram of this configuration is included in the appendix.

<table><tr><td>Pipe Setting</td><td>End of the Pipe</td><td>Other End of the Pipe</td></tr><tr><td>1st</td><td>(10,15)</td><td>(30,15)</td></tr><tr><td>2nd</td><td>(50,15)</td><td>(70,15)</td></tr></table>

Our tests collected the following information about this algorithm:

<table><tr><td> $\mu$ </td><td>.0042m/h</td></tr><tr><td> $\sigma^{2}$ </td><td> $1.68 \times 10^{-6}$ </td></tr><tr><td>min</td><td>.00217m/h</td></tr><tr><td>max</td><td>.0117m/h</td></tr></table>

This algorithm is useful because it uses so few moves, has a high degree of uniformity (as denoted by the low variance) and can successfully irrigate the entire field. This algorithm is perfect for farmers who would rather be shooting soda cans off of a fence post than lugging around a heavy aluminum tube.

## The Passive-Aggressive Farmer Algorithm

For this algorithm, we arranged the pipes in a pattern resembling an “H.” See appendix for a diagram of this configuration

<table><tr><td>Pipe Setting</td><td>End of the Pipe</td><td>Other End of the Pipe</td></tr><tr><td>1st</td><td>(16,5)</td><td>(16,25)</td></tr><tr><td>2nd</td><td>(30,15)</td><td>(50,15)</td></tr><tr><td>3rd</td><td>(64,5)</td><td>(64,25)</td></tr></table>

Our tests collected the following information about this algorithm:

<table><tr><td> $\mu$ </td><td>.0057m/h</td></tr><tr><td> $\sigma^{2}$ </td><td> $3.92 \times 10^{-6}$ </td></tr><tr><td>min</td><td>.00254m/h</td></tr><tr><td>max</td><td>.0161m/h</td></tr></table>

This algorithm neither improves much upon the stability of the system (as described in a previous section) nor saves time by using few pipe moves. Therefore, this algorithm would be perfect for an indecisive or passive-aggressive farmer.

## The Conservative Farmer Algorithm

For this four step algorithm, we arranged the pipes in with a square grid. See appendix for a diagram of this configuration

<table><tr><td>Pipe Setting</td><td>End of the Pipe</td><td>Other End of the Pipe</td></tr><tr><td>1st</td><td>(10,5)</td><td>(10,25)</td></tr><tr><td>2nd</td><td>(30,5)</td><td>(30,25)</td></tr><tr><td>3rd</td><td>(50,5)</td><td>(50,25)</td></tr><tr><td>4th</td><td>(70,5)</td><td>(70,25)</td></tr></table>

Our tests collected the following information about this algorithm:

<table><tr><td> $\mu$ </td><td>.0064m/h</td></tr><tr><td> $\sigma^{2}$ </td><td> $4.18 \times 10^{-6}$ </td></tr><tr><td>min</td><td>.00263m/h</td></tr><tr><td>max</td><td>.0107m/h</td></tr></table>

This algorithm is very stable (as previously described). It is perfect for a farmer that is very careful and untrusting of the wind.

## The Creative Farmer Algorithm

For this three step algorithm, we arranged the pipes on a grid of equalateral triangles. See appendix for a diagram of this configuration

<table><tr><td>Pipe Setting</td><td>End of the Pipe</td><td>Other End of the Pipe</td></tr><tr><td>1st</td><td>(10,5)</td><td>(10,25)</td></tr><tr><td>2nd</td><td>(30,5)</td><td>(30,25)</td></tr><tr><td>3rd</td><td>(50,5)</td><td>(50,25)</td></tr><tr><td>4th</td><td>(70,5)</td><td>(70,25)</td></tr></table>

Our tests collected the following information about this algorithm:

<table><tr><td> $\mu$ </td><td>.0065m/h</td></tr><tr><td> $\sigma^{2}$ </td><td> $2.44 \times 10^{-6}$ </td></tr><tr><td>min</td><td>.00272m/h</td></tr><tr><td>max</td><td>.0102m/h</td></tr></table>

This algorithm is the second most uniform and has the largest minimum of the algorithms proposed. The setup is somewhat complicated as the grid is an equilateral triangle. Some farmers may be up to the task. It is perfect for a farmer that regularly plays Sudoku and stopped watching MacGuyver because he claimed he lacked of ingenuity.

## 8 Conclusion

In this paper we proposed several fantastic algorithms for field irrigation. Surely, the average farmer will have reason for jubilation after receiving a new Rain Bird irrigation system and implementing his or her favorite irrigation algorithm. Before throwing a sock hop at the local high school gymnasium, the farmer should read our conclusion as we outline what algorithms work better in what situations. The following table serves as a summary:

<table><tr><td>Fastest Algorithm</td><td>The Lazy Farmer Algorithm</td><td>25 hours 22 minutes over 4 days</td></tr><tr><td>Most Uniform Algorithm</td><td>The Lazy Farmer Algorithm</td><td> $\sigma^2 \approx 1.68 \times 10^{-6}$ </td></tr><tr><td>Most Stable Algorithm</td><td>The Conservative Farmer Algorithm</td><td>Most resistant to wind</td></tr></table>

Thus, there are only two algorithms that a farmer should consider. The Conservative Farmer Algorithm should be used in windy conditions or if the level of the field is somewhat nonuniform. The Lazy Farmer Algorithm should be used otherwise because it is the fastest, easiest and most uniform.

Although some specific parameters of our system may change, the methods we used to evaluate our proposal are general. We based our algorithms off of experimental data from the sprinkler manufacturer. We also looked at sprinklers from other manufacturers with specs similar to those given in the problem and found the radii do not change much. If a different setting were used, however, we could use our methods to analyze the system.

## 9 References

Louie and Selker. “Sprinkler Head Maintenance Effects on Water Application Uniformity.” Journal of Irrigation and Drainage Engineering
May/June 2000

Smajstrla et al. “Lawn Sprinkler Selection and Layout for Uniform Water Application.” University of Florida. <http://edis.ifas.ufl.edu/AE084/>

Eisenhauer, Martin, and Hoffman. Irrigation Principles and Management (Chapter 11). University of Nebraska, Lincoln.

Rain Bird Sprinkler information <http://rainbird.com/pdf/aq/imptmtrc70h.pdf>